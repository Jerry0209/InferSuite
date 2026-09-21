// naivebayes.scala — Spark ML multinomial Naive Bayes trained on a real corpus, looped for a
// fixed wall time (spark-shell -i). Renaissance's naive-bayes trains the same estimator on a
// 100-row sample copied 8 000 times; this trains it on RCV1-v2 (Reuters news, 518 k documents,
// 47 k tf-idf features, 53 topics) from the LIBSVM multiclass collection.
// Env: RD_LIBSVM (libsvm file), RD_SECONDS.
import org.apache.spark.ml.classification.NaiveBayes
val path = sys.env("RD_LIBSVM"); val seconds = sys.env.getOrElse("RD_SECONDS", "600").toLong
val t0 = System.nanoTime
val data = spark.read.format("libsvm").option("numFeatures", "47236").load(path)
  .withColumn("label", $"label" - 1).cache()   // labels 1..53 -> 0..52
val n = data.count()
println(f"[rd] corpus loaded: $n documents in ${(System.nanoTime - t0) / 1e9}%.1f s")
var pass = 0
while ((System.nanoTime - t0) / 1e9 < seconds) {
  val model = new NaiveBayes().setModelType("multinomial").fit(data)
  val acc = model.transform(data).filter($"label" === $"prediction").count().toDouble / n
  pass += 1
  println(f"[rd] pass $pass done at ${(System.nanoTime - t0) / 1e9}%.0f s; train accuracy ${acc}%.3f")
}
println(s"[rd] finished $pass passes")
System.exit(0)

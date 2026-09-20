// pagerank.scala — Spark PageRank on a real graph, looped for a fixed wall time (spark-shell -i).
// The algorithm is the RDD join formulation of Spark's own SparkPageRank example, which is
// also what Renaissance's page-rank benchmark runs -- here on the SNAP LiveJournal edge list
// (69 M edges) instead of Renaissance's 7.6 M-edge web-BerkStan sample.
// Env: RD_EDGES (edge list, "src<TAB>dst" lines, # comments), RD_ITERS (per pass), RD_SECONDS.
import org.apache.spark.storage.StorageLevel
val edges = sys.env("RD_EDGES"); val iters = sys.env.getOrElse("RD_ITERS", "3").toInt
val seconds = sys.env.getOrElse("RD_SECONDS", "600").toLong
val t0 = System.nanoTime
val lines = sc.textFile(edges, 64).filter(l => !l.startsWith("#"))
val links = lines.map { s => val p = s.split("\\s+"); (p(0).toLong, p(1).toLong) }
  .distinct().groupByKey().persist(StorageLevel.MEMORY_ONLY)
val nLinks = links.count()
println(s"[rd] graph loaded: $nLinks source vertices in ${(System.nanoTime - t0) / 1e9}%.1f s")
var pass = 0
while ((System.nanoTime - t0) / 1e9 < seconds) {
  var ranks = links.mapValues(_ => 1.0)
  for (i <- 1 to iters) {
    val contribs = links.join(ranks).values.flatMap { case (urls, rank) =>
      val size = urls.size; urls.map(url => (url, rank / size)) }
    ranks = contribs.reduceByKey(_ + _).mapValues(0.15 + 0.85 * _)
  }
  val top = ranks.top(3)(Ordering.by(_._2))
  pass += 1
  println(s"[rd] pass $pass done at ${(System.nanoTime - t0) / 1e9}%.0f s; top rank ${top.head}")
}
println(s"[rd] finished $pass passes")
System.exit(0)

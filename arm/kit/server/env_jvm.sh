# env_jvm.sh — paths and x86-equal knobs for the eight JVM Server workloads (tomcat, finagle-chirper,
# finagle-http, cassandra-ycsb20m, kafka-20g, naivebayes-rcv1, pagerank-livejournal, neo4j-livejournal)
# on the Graviton5 box. Sourced by run_server.sh (env_*.sh): exports only, no side effects.
# Built by install_jvm_stack.sh + setup_*.sh; provenance in arm/data/interim/server/prep_jvm.md.
_ARCH="$(dpkg --print-architecture)"
export JAVA17_HOME="/usr/lib/jvm/java-17-openjdk-$_ARCH"      # apt openjdk-17-jdk-headless 17.0.20.1
export JAVA21_HOME="/usr/lib/jvm/java-21-openjdk-$_ARCH"      # apt openjdk-21-jdk-headless 21.0.12.1
export REALDATA_INFRA="$HOME/realdata-infra" JVMBENCH_INFRA="$HOME/jvmbench-infra"   # x86 layout

# DaCapo tomcat / Renaissance finagle-* (bench_jvm_common.sh, bench_dacapo.sh, bench_renaissance.sh)
export JAVA="$JAVA21_HOME/bin/java"
export DACAPO_JAR="$JVMBENCH_INFRA/dacapo-23.11-MR2-chopin.jar"      # data tree beside it, pruned to tomcat/cassandra/kafka
export RENAISSANCE_JAR="$JVMBENCH_INFRA/renaissance-gpl-0.16.1.jar"
# decision 2: x86 G1 ergonomics on 62 GB gave 1000 MB initial / 15,944 MB max; ergonomics here would pick ~94 GB.
# x86 bench_jvm_common.sh has no flags hook: the port must put this before -jar.
export JVM_SUITE_OPTS="-Xms1000m -Xmx15944m"

# cassandra-ycsb20m (bench_cassandra.sh)
export CAS_JAVA_HOME="$JAVA17_HOME" YCSB_JAVA_HOME="$JAVA21_HOME"
export CAS_HOME="$REALDATA_INFRA/cassandra" YCSB_HOME="$REALDATA_INFRA/ycsb" CAS_DS="$REALDATA_INFRA/datasets/cassandra-ycsb"
# decision 3: apt libjemalloc2 5.3.0. Must reach the node via `systemd-run -E CASSANDRA_LIBJEMALLOC=...`: unset,
# bin/cassandra's search (sort -ru) picks /usr/local/lib/libjemalloc.so.2 = FeedSim's 5.2.1 once env_native's build exists.
export CASSANDRA_LIBJEMALLOC="/usr/lib/$(uname -m)-linux-gnu/libjemalloc.so.2"
# GC threads (16, as x86) are pinned in $CAS_HOME/conf/jvm17-server.options by setup_cassandra_ycsb.sh: nothing to pass.

# kafka-20g (bench_kafka.sh)
export KAFKA_JAVA_HOME="$JAVA21_HOME"
export KAFKA_HOME="$REALDATA_INFRA/kafka" KAFKA_DS="$REALDATA_INFRA/datasets/kafka"
export KAFKA_CONF="$KAFKA_HOME/config/infersuite-server.properties"

# naivebayes-rcv1 / pagerank-livejournal (bench_spark.sh)
export SPARK_JAVA="$JAVA21_HOME/bin/java" SPARK_HOME="$REALDATA_INFRA/spark"
export RD_INPUT_LIVEJOURNAL="$REALDATA_INFRA/datasets/livejournal/soc-LiveJournal1.txt"
export RD_INPUT_RCV1="$REALDATA_INFRA/datasets/rcv1/rcv1_test.multiclass"

# neo4j-livejournal (bench_neo4j.sh); client venv: Python 3.13.13 (uv) + neo4j 6.3.1 + neo4j-rust-ext 6.3.1.0 (aarch64 wheel)
export NEO_JAVA_HOME="$JAVA21_HOME"
export NEO_HOME="$REALDATA_INFRA/neo4j" NEO_DB=livejournal NEO_DS="$REALDATA_INFRA/datasets/livejournal"
export CLIENT_PY="$REALDATA_INFRA/venv/bin/python"
unset _ARCH

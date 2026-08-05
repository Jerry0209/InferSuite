### perf knobs

sudo sysctl -w kernel.perf_event_paranoid=-1 kernel.kptr_restrict=0

# make it survive reboot:
printf 'kernel.perf_event_paranoid = -1\nkernel.kptr_restrict = 0\n' \
  | sudo tee /etc/sysctl.d/99-infersuite-perf.conf

sudo sysctl -w kernel.perf_event_paranoid=-1 kernel.kptr_restrict=0
printf 'kernel.perf_event_paranoid = -1\nkernel.kptr_restrict = 0\n' \
  | sudo tee /etc/sysctl.d/99-infersuite-perf.conf


### Docker group
sudo usermod -aG docker $USER
newgrp docker      # or log out/in; verify with: docker ps

### k3s kubeconfig
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/k3s.yaml
sudo chown $USER:$USER ~/.kube/k3s.yaml && chmod 600 ~/.kube/k3s.yaml
echo 'export KUBECONFIG=~/.kube/k3s.yaml' >> ~/.bashrc && export KUBECONFIG=~/.kube/k3s.yaml
kubectl get nodes

### Passwordless sudo
echo "$USER ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/90-infersuite
sudo chmod 440 /etc/sudoers.d/90-infersuite



# Pin file FIRST, or apt drags libnvidia-* to 580.173.02 against the loaded
# 580.159.03 and kills the running vLLM engine.
sudo tee /etc/apt/preferences.d/nvidia-driver-from-ubuntu-archive >/dev/null <<'EOF'
Package: nvidia-driver-* nvidia-dkms-* nvidia-kernel-* nvidia-utils-* nvidia-compute-utils-* nvidia-firmware-* libnvidia-* linux-modules-nvidia-* linux-objects-nvidia-* linux-signatures-nvidia-* xserver-xorg-video-nvidia-*
Pin: release l=NVIDIA CUDA
Pin-Priority: 400
EOF

sudo dpkg --configure -a

### SWE-agent
cd ~/InferSuite/agentic/swe_agent
mkdir -p external && git clone https://github.com/SWE-agent/SWE-agent.git external/SWE-agent
python3 -m venv .venv
./.venv/bin/pip install -e external/SWE-agent
./.venv/bin/sweagent --help


### litellm venv
cd ~/InferSuite/agentic/openclaw
python3 -m venv .venv_litellm
./.venv_litellm/bin/pip install "litellm[proxy]"

### GLM API key 
install -m 600 /dev/null ~/.glm_key
read -rs GLM_TMP && printf '%s' "$GLM_TMP" > ~/.glm_key && unset GLM_TMP


[ -s ~/.glm_key ] && echo "present, $(wc -c < ~/.glm_key) bytes, perms $(stat -c %a ~/.glm_key)"


K=$(tr -d '[:space:]' < ~/.glm_key)
curl -s -o /dev/null -w 'HTTP %{http_code}\n' -H "Authorization: Bearer $K" https://api.z.ai/api/paas/v4/models
curl -s -H "Authorization: Bearer $K" https://api.z.ai/api/paas/v4/models | grep -q '"glm-5.2"' \
  && echo "glm-5.2 available" || echo "glm-5.2 NOT in model list"
unset K



### WildClawBench / OpenClaw


### Figure pipeline
 conda activate infersuite-full
./measure.sh plots
PLOT_SPEC=local_agents/SWE_clean/plot_spec.json python3 local_agents/kit/validate/audit_plots.py

### Superseded set
cd ~/InferSuite/local_agents/kit
./run_glm_campaign.sh preflight        # no spend
./run_glm_campaign.sh isolation-test   # applies knobs, verifies, reverts, re-verifies
./run_glm_campaign.sh dryrun           # zero-multiplexing gate, all 8 groups 100% enabled
DATA_ROOT=... SWE_INSTANCES="scikit-learn__scikit-learn-25232" REPEATS=1 \
  ./run_glm_campaign.sh campaign swe   # one episode end-to-end first
# then the full 12-episode run with the command above

sudo systemctl stop k3s
sudo /usr/local/bin/k3s-killall.sh
pgrep -af "vllm|EngineCore|milvus|pd-sidecar"    # wait until this prints nothing


cd ~/InferSuite/local_agents/kit

./run_glm_campaign.sh dryrun          # zero-mux gate: all 8 groups must report 100% enabled

DATA_ROOT=$HOME/InferSuite/local_agents/superseded_40min/data \
SWE_INSTANCES="scikit-learn__scikit-learn-25232" REPEATS=1 \
  ./run_glm_campaign.sh campaign swe                    # one episode, ~10-40 min, real spend

DATA_ROOT=$HOME/InferSuite/local_agents/superseded_40min/data \
SWE_INSTANCES="scikit-learn__scikit-learn-25232 astropy__astropy-14096 sympy__sympy-14248 django__django-10097" \
  ./run_glm_campaign.sh campaign swe                    # full 12 episodes, ~2.5-4 h





```text
~/InferSuite
│
├── measure.sh                          # optional entry point (SWE_clean profile: temp 0.6, REPEATS=1)
│                                       #   ── our reproduction called the kit directly instead
│
├── local_agents/kit/           # ════ THE CAMPAIGN KIT (everything runs from here) ════
│   ├── run_glm_campaign.sh             # the runner: preflight → dryrun → isolation+ISO-PROOF →
│   │                                   #   proxy → episodes → capture stack → teardown; stages+resume
│   ├── campaign.conf                   # all knobs: instances, REPEATS, SWE_TEMP, CPU partition, key path
│   ├── litellm_glm.yaml                # proxy config → GLM-5.2 endpoint (key via env, never in file)
│   ├── validate_glm_agents.py          # post-hoc gates E1–E11 (incl. E7 action-uniqueness = loop check)
│   ├── audit_plots.py                  # recomputes every plotted number from raw → "ALL MATCH"
│   ├── gen_lanes_leaf.sh               # derives per-CPU lanes + leaf symbol tables from rec_*.data
│   ├── plot_glm_results.py             # main plotter → 12 figures + values_dump.json (spec-driven)
│   ├── plot_call_structure.py          #   companion plotters, same PLOT_SPEC mechanism
│   ├── plot_internal_tools.py          #   (traj-anchored per-call CPU attribution)
│   ├── plot_calls_vs_bursts.py
│   ├── plot_harness_scaling.py         # cross-campaign turns^2.7 law (reads SWE_clean + archive)
│   ├── campaign.log                    # (generated) master log — the monitor watched this
│   └── proxy.log                       # (generated) litellm round-trips; overwritten per campaign
│
├── agentic/swe_agent/                  # ════ THE HARNESS THE KIT DRIVES ════
│   ├── external/SWE-agent/             # vendored SWE-agent v1.1.0 (3ea751c0) — incl. the buggy
│   │   └── tools/review_on_submit_m/bin/submit    #   f-string submit tool (the django finding)
│   └── .venv/                          # sweagent CLI env (gitignored; rebuilt from external/)
│
├── agentic/openclaw/.venv_litellm/     # litellm 1.89.4 proxy env (housekeeping cores; gitignored)
│
├── local_agents/superseded_40min/      # ════ THE REPRODUCTION CAMPAIGN (this session) ════
│   ├── data/
│   │   ├── glm_swe_{scikit-learn,astropy,sympy,django}/run_{1..3}/   # 12 temp-0 episodes
│   │   ├── glm-t06_swe_django/run_{1,2}/                             # 2 temp-0.6 episodes
│   │   │   ── per episode: ───────────────────────────────────────
│   │   │   agent.log                   # harness narration (STEP markers = turns)
│   │   │   metadata.json               # provenance: model, temperature, cgroup names
│   │   │   traj/<inst>/<inst>.traj     # full trajectory (thought/action/observation per step)
│   │   │   cpustat_scope{1,2,3}.tsv    # 10 Hz exact CPU: 1=harness 2=tool 3=litellm
│   │   │   windows.tsv                 # shuffled counter-rotation schedule (epoch brackets)
│   │   │   group_{fpbr,cache,mlp,fe,fe_lat,core_ports,dram_bw,priv}_wNNN.txt   # zero-mux counts
│   │   │   tma_cont.csv                # continuous top-down census (TMA L1+L2 source)
│   │   │   rec_scope{1,2,3}.data       # 99 Hz perf records (attribution only)
│   │   │   scope{1,2,3}_{dso,comm}.txt # what-program/library tables from the records
│   │   │   procstat_partition.tsv      # partition witness (gate E11)
│   │   │   DONE                        # resume marker
│   │   ├── plot_spec.json              # featured-run selection (the 5-entry spec)
│   │   └── plots/                      # (generated) glm_*.png + values_dump.json
│   │       └── compare/                # (generated) cmp_*.png + moh_featured/ (his figures)
│   │
├── local_agents/SWE_clean/             # the certified thesis campaign (read-only reference:
│   │                                   #   data/, plots/, plot_spec.json — the turns^2.7 inputs)
│   └── analysis.md                     # ← repo root: the comparison write-up
│
└── (outside the repo, still required)
    ~/.glm_key                                     # API key (bare string, 600)
    ~/llm-service-kernel-latest/archive/certified_glm_40min/   # Mohamad's raw campaign (comparison baseline)
    docker: swebench/sweb.eval.x86_64.*            # per-task sandbox images (pulled on demand)
    /usr/lib/linux-tools-6.8*/perf                 # the working perf binary (glob!)

```

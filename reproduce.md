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
PLOT_SPEC=local_agents/SWE_clean/plot_spec.json python3 local_agents/scripts/glm/audit_plots.py

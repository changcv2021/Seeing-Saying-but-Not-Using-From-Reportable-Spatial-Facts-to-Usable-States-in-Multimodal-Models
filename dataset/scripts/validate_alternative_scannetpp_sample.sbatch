#!/usr/bin/env bash
#SBATCH --job-name=sc_sp7m_probe
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:10:00
#SBATCH --output=artifacts/upstream_media/spar7m_acquisition/slurm/scannetpp_probe_%j.out
#SBATCH --error=artifacts/upstream_media/spar7m_acquisition/slurm/scannetpp_probe_%j.err

set -euo pipefail

raw_root=artifacts/upstream_media/spar7m_raw/scannetpp
probe_root=artifacts/upstream_media/spar7m_acquisition/probes

mkdir -p "$raw_root/archives" "$probe_root"

scene_archive="$raw_root/archives/fde8a3b4c0.tar.gz"
scene_url=https://huggingface.co/datasets/HarrisonPENG/scannetpp/resolve/main/fde8a3b4c0.tar.gz
curl --fail --location --retry 8 --retry-all-errors --continue-at - \
  --output "$scene_archive" "$scene_url"
printf '%s  %s\n' \
  ecb407f7fb3ee287d917e43bfb8e23d6887006b1bf4e7186f97a892ad0322db4 \
  "$scene_archive" | sha256sum --check
tar -tzf "$scene_archive" > "$probe_root/fde8a3b4c0.members.txt"
if ! rg -q 'fde8a3b4c0/images/frame_003950([.]jpg)?$' "$probe_root/fde8a3b4c0.members.txt"; then
  echo 'Required RGB frame fde8a3b4c0/images/frame_003950 was not found' >&2
  exit 20
fi

fallback_video="$raw_root/00777c41d4.mp4"
fallback_url=https://huggingface.co/datasets/nkkbr/ViCA-322K/resolve/main/video/scannetpp/00777c41d4.mp4
curl --fail --location --retry 8 --retry-all-errors --continue-at - \
  --output "$fallback_video" "$fallback_url"
printf '%s  %s\n' \
  f47413b2e59631dc8bd4c1b279acd15debf7b06ec05356a1917798ee3e3c1ead \
  "$fallback_video" | sha256sum --check

if command -v ffprobe >/dev/null 2>&1; then
  ffprobe -v error -count_frames -select_streams v:0 \
    -show_entries stream=width,height,r_frame_rate,avg_frame_rate,nb_frames,nb_read_frames,duration \
    -of json "$fallback_video" > "$probe_root/00777c41d4.ffprobe.json"
fi

stat -c '%s %n' "$scene_archive" "$fallback_video"
echo PROBE_PASS

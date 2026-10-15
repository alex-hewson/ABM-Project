#!/bin/bash
# Slurm job array for the value trader sweep (experiments/value_sweep.py): one job per combination,
# numbered 0 (no value traders) to 48. Submit from the project root:
#
#     sbatch cluster/value_sweep.slurm
#
# Check on it with `squeue -u $USER`. Each job's output goes to logs/value_sweep_<number>.out.
# When the jobs are done, copy results/value_sweep/ back to the laptop and run
#     python -m experiments.value_sweep collect
#
# Before the first submission (once):
#   - a Python 3.12 or newer virtual environment with numpy, matplotlib and pytest, at ~/abm-env
#     (see the README, "Running on a cluster");
#   - mkdir -p logs
#
# Settings to check against the cluster:
#   --cpus-per-task   CPUs each job uses. 8 is a safe start; at most the CPUs on one node.
#   --array=0-48%10   %10 runs at most 10 jobs at once, so the sweep does not fill a shared cluster.
#   --mem-per-cpu     each worker needs well under 1 GB.

#SBATCH --job-name=value_sweep
#SBATCH --partition=cpu
#SBATCH --array=0-48%10
#SBATCH --cpus-per-task=8
#SBATCH --mem-per-cpu=1G
#SBATCH --output=logs/value_sweep_%a.out

source ~/abm-env/bin/activate
python -m experiments.value_sweep run --index "$SLURM_ARRAY_TASK_ID" --workers "$SLURM_CPUS_PER_TASK"

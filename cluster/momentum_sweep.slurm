#!/bin/bash
# Slurm job array for the momentum trader sweep (experiments/momentum_sweep.py): one job per
# combination, numbered 0 to 241 (`python -m experiments.momentum_sweep list`). Submit from the
# project folder, with the Python environment switched on (sbatch passes it on to the jobs):
#
#     sbatch --cpus-per-task=16 --time=01:00:00 cluster/momentum_sweep.slurm
#
# Check on it with `squeue -u $USER`. Each job's output goes to logs/momentum_sweep_<number>.out.
# When the jobs are done, copy results/momentum_sweep/ back to the laptop and run
#     python -m experiments.momentum_sweep collect
#
# Settings to check against the cluster (an option given to sbatch overrides the line below):
#   --cpus-per-task   CPUs each job uses; at most the CPUs on one node.
#   --array=0-241%10  %10 runs at most 10 jobs at once, so the sweep does not fill a shared cluster.
#   --time            a limit lets Slurm fit the jobs into gaps sooner; a job in the value trader
#                     sweep took about 17 minutes with 16 CPUs.

#SBATCH --job-name=momentum_sweep
#SBATCH --partition=cpu
#SBATCH --array=0-241%10
#SBATCH --cpus-per-task=8
#SBATCH --mem-per-cpu=1G
#SBATCH --output=logs/momentum_sweep_%a.out

# Which Python the job is using, so the log shows it.
echo "node: $(hostname)   python: $(command -v python)   $(python --version 2>&1)"
# Extra options for `run` can be passed in SWEEP_ARGS, e.g. SWEEP_ARGS=--shock-only.
python -u -m experiments.momentum_sweep run --index "$SLURM_ARRAY_TASK_ID" --workers "$SLURM_CPUS_PER_TASK" ${SWEEP_ARGS:-}

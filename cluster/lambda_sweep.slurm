#!/bin/bash
# Slurm job array for the mean entry depth trial (experiments/lambda_sweep.py, D40): one job per
# setup and lambda_0, numbered 0 to 29 (`python -m experiments.lambda_sweep list`; 0 to 5 are the
# fixed-depth controls). Submit from the project folder, with the Python environment switched on
# (sbatch passes it on to the jobs):
#
#     sbatch cluster/lambda_sweep.slurm
#
# Check on it with `squeue -u $USER`. Each job's output goes to logs/lambda_sweep_<number>.out.
# When the jobs are done, copy results/lambda_sweep/ back to the laptop and run
#     python -m experiments.lambda_sweep collect
#
# Each job is 4 runs of 120,000 steps at N_A = 500, one CPU each.
# No time limit and no limit on jobs at once: on this cluster's first come, first served queue they
# do not help the jobs start sooner.

#SBATCH --job-name=lambda_sweep
#SBATCH --partition=cpu
#SBATCH --array=0-29
#SBATCH --cpus-per-task=4
#SBATCH --mem-per-cpu=2G
#SBATCH --output=logs/lambda_sweep_%a.out

# Which Python the job is using, so the log shows it.
echo "node: $(hostname)   python: $(command -v python)   $(python --version 2>&1)"
python -u -m experiments.lambda_sweep run --index "$SLURM_ARRAY_TASK_ID" --workers "$SLURM_CPUS_PER_TASK" ${SWEEP_ARGS:-}

#!/bin/bash
# Slurm job array for the phase diagram sweep (experiments/phase_sweep.py): one job per combination,
# numbered 0 to 175 (`python -m experiments.phase_sweep list`; the N_A = 1000 ones first). Submit from
# the project folder, with the Python environment switched on (sbatch passes it on to the jobs):
#
#     sbatch cluster/phase_sweep.slurm
#
# Check on it with `squeue -u $USER`. Each job's output goes to logs/phase_sweep_<number>.out.
# When the jobs are done, copy results/phase_sweep/ back to the laptop and run
#     python -m experiments.phase_sweep collect
#
# A job takes about 30 minutes at N_A = 1000 with 16 CPUs, and about 5 at N_A = 125. More than 16 CPUs
# does not help: the 16 normal-times runs are the longest part, one CPU each.
# No time limit and no limit on jobs at once: on this cluster's first come, first served queue they
# do not help the jobs start sooner.

#SBATCH --job-name=phase_sweep
#SBATCH --partition=cpu
#SBATCH --array=0-175
#SBATCH --cpus-per-task=16
#SBATCH --mem-per-cpu=2G
#SBATCH --output=logs/phase_sweep_%a.out

# Which Python the job is using, so the log shows it.
echo "node: $(hostname)   python: $(command -v python)   $(python --version 2>&1)"
python -u -m experiments.phase_sweep run --index "$SLURM_ARRAY_TASK_ID" --workers "$SLURM_CPUS_PER_TASK" ${SWEEP_ARGS:-}

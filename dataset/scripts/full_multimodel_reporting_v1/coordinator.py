"""Use the immutable controller with a reporting-only fullchain extension."""
from report import EXTENSION,verify_extension
import controller

if __name__=='__main__':
    verify_extension()
    # Only the script used for future sbatch commands changes. All request
    # selection, gates, budgets, inference, scoring and source hashes stay frozen.
    controller.CODE=EXTENSION
    controller.main()

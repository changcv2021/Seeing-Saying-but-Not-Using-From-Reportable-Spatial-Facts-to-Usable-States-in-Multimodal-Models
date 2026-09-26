"""Active common entry for NEW SWS work; frozen v1 workers remain untouched."""
from common import *
from common import arguments as old_arguments, setup as old_setup
from review_policy_v2 import CONFIG, effective_policy, execution_decision


def arguments(description):
    parser = old_arguments(description)
    parser.set_defaults(config=CONFIG)
    return parser


def setup(args):
    config, root = old_setup(args)
    effective_policy(config)
    return config, root

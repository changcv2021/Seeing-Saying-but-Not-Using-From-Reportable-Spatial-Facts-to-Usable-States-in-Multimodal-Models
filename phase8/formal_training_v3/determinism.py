"""Same numerical backend for every arm and fresh-process resume validation."""
import os


def configure():
    # Must precede CUDA context/model creation in each training worker.
    os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':4096:8'
    import torch
    torch.use_deterministic_algorithms(True, warn_only=False)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cuda.enable_flash_sdp(False)
    torch.backends.cuda.enable_mem_efficient_sdp(False)
    torch.backends.cuda.enable_cudnn_sdp(False)
    torch.backends.cuda.enable_math_sdp(True)
    return dict(torch_version=torch.__version__, deterministic_algorithms=True,
        cudnn_deterministic=True, cudnn_benchmark=False, tf32=False,
        cublas_workspace_config=os.environ['CUBLAS_WORKSPACE_CONFIG'],
        sdpa_backend='math_only', tolerance_not_relaxed=True,
        all_training_arms_same_backend=True)

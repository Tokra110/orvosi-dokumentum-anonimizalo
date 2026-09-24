import importlib.metadata as metadata


def test_runtime_environment_has_no_torch_stack():
    installed = {dist.metadata["Name"].lower() for dist in metadata.distributions()}
    banned = sorted(
        name
        for name in installed
        if name in {"torch", "torchvision", "triton"}
        or name.startswith("nvidia-")
    )

    assert banned == []

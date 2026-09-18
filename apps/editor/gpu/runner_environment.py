"""Explicit non-secret runner settings needed to reproduce GPU memory behavior."""

OFFLINE_ENV = {
    'HF_HUB_OFFLINE': '1',
    'HF_HUB_DISABLE_TELEMETRY': '1',
    'HF_MODULES_CACHE': '/tmp/hf-modules',
}
RUNTIME_VALUES = {
    'VLLM_PLE_CPU_OFFLOAD': {'0', '1'},
    'NCCL_P2P_LEVEL': {'LOC', 'NVL', 'PIX', 'PXB', 'PHB', 'SYS'},
}


def as_mapping(values):
    return dict(value.split('=', 1) for value in values or [] if '=' in value)


def validate_environment(environment):
    if not isinstance(environment, dict) or set(environment) - set(OFFLINE_ENV) - set(RUNTIME_VALUES):
        raise RuntimeError('UNSUPPORTED_PACKAGED_RUNNER_ENVIRONMENT')
    if any(environment.get(key) != value for key, value in OFFLINE_ENV.items()):
        raise RuntimeError('OFFLINE_RUNNER_ENVIRONMENT_REQUIRED')
    if any(environment[key] not in values for key, values in RUNTIME_VALUES.items() if key in environment):
        raise RuntimeError('INVALID_RUNNER_ENVIRONMENT_VALUE')


def capture_environment(container, image):
    actual = as_mapping(container['Config'].get('Env'))
    defaults = as_mapping(image['Config'].get('Env'))
    overrides = {key for key, value in actual.items() if defaults.get(key) != value}
    unsupported = overrides - set(OFFLINE_ENV) - set(RUNTIME_VALUES)
    if unsupported:
        # Never copy or report values of unknown variables, especially secrets.
        raise RuntimeError('UNSUPPORTED_RUNNER_ENVIRONMENT_OVERRIDE:' + ','.join(sorted(unsupported)))
    result = {**OFFLINE_ENV, **{key: actual[key] for key in RUNTIME_VALUES if key in actual}}
    validate_environment(result)
    return result

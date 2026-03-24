import yamcs.pymdb as Y

service = Y.System("SERVICE-EPS")
service_type_id = 132

base_cmd = Y.Command(
    system=service,
    name="base",
    abstract=True,
    base="/PUS/pus-tc",
    assignments={"type": service_type_id},
)

fetch_eps_cmd = Y.Command(
    system=service,
    base=base_cmd,
    assignments={
        "subtype": 1,
        "apid": 42,
    },
    name="FetchEPSData",
    arguments=[],
)

eps_voltage = Y.IntegerParameter(
    system=service,
    name="EPS_VOLTAGE",
    encoding=Y.int32_t,
)

eps_current_in = Y.IntegerParameter(
    system=service,
    name="EPS_CURRENT_IN",
    encoding=Y.int32_t,
)

eps_current_out = Y.IntegerParameter(
    system=service,
    name="EPS_CURRENT_OUT",
    encoding=Y.int32_t,
)

eps_temperature = Y.IntegerParameter(
    system=service,
    name="EPS_TEMPERATURE",
    encoding=Y.int32_t,
)

pcu_telemetry = Y.Container(
    system=service,
    base="/PUS/pus-tm",
    name="EPSTelemetry",
    condition=Y.AndExpression(
        Y.EqExpression("/PUS/pus-tm/type", service_type_id),
        Y.EqExpression("/PUS/pus-tm/subtype", 0),
    ),
    entries=[
        Y.ParameterEntry(eps_voltage),
        Y.ParameterEntry(eps_current_in),
        Y.ParameterEntry(eps_current_out),
        Y.ParameterEntry(eps_temperature),
    ],
)

print(service.dumps())

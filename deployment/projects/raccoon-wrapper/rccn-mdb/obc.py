import yamcs.pymdb as Y

service = Y.System("SERVICE-OBC")
service_type_id = 131

base_cmd = Y.Command(
    system=service,
    name="base",
    abstract=True,
    base="/PUS/pus-tc",
    assignments={"type": service_type_id},
)

get_temperature = Y.Command(
    system=service,
    base=base_cmd,
    assignments={
        "subtype": 1,
        "apid": 42,
    },
    name="GetTemperature",
    arguments=[],
)

obc_temperature = Y.IntegerParameter(
    system=service,
    name="OBC_Temperature",
    encoding=Y.int32_t,
)

pcu_telemetry = Y.Container(
    system=service,
    base="/PUS/pus-tm",
    name="OBCTelemetry",
    condition=Y.AndExpression(
        Y.EqExpression("/PUS/pus-tm/type", service_type_id),
        Y.EqExpression("/PUS/pus-tm/subtype", 0),
    ),
    entries=[
        Y.ParameterEntry(
            obc_temperature
        ),
    ],
)

print(service.dumps())

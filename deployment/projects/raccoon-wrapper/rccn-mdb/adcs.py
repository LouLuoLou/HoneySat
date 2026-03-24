import yamcs.pymdb as Y

service = Y.System("SERVICE-ADCS")
service_type_id = 133

base_cmd = Y.Command(
    system=service,
    name="base",
    abstract=True,
    base="/PUS/pus-tc",
    assignments={
        "type": service_type_id,
        "apid": 42,
    },
)

fetch_adcs_mag_cmd = Y.Command(
    system=service,
    base=base_cmd,
    assignments={"subtype": 0},
    name="Fetch_ADCS_Mag_Data",
    arguments=[],
)

fetch_adcs_gyro_cmd = Y.Command(
    system=service,
    base=base_cmd,
    assignments={"subtype": 1},
    name="Fetch_ADCS_Gyro_Data",
    arguments=[],
)

fetch_adcs_sun_cmd = Y.Command(
    system=service,
    base=base_cmd,
    assignments={"subtype": 2},
    name="Fetch_ADCS_Sun_Data",
    arguments=[],
)

# adcs_mag = Y.ArrayParameter(
#     system=service,
#     name="ADCS_MAG",
#     data_type=Y.FloatDataType(bits=32),
#     # encoding=Y.float32_t,
#     length=3,
# )

# adcs_gyro = Y.ArrayParameter(
#     system=service,
#     name="ADCS_GYRO",
#     data_type=Y.FloatDataType(bits=32),
#     # encoding=Y.,
#     length=3,
# )

adcs_gyro = []
adcs_mag = []
for c in 'XYZ':
    adcs_gyro.append(Y.FloatParameter(
        system=service,
        name=f"ADCS_GYRO_{c}",
        encoding=Y.float32le_t,
    ))
    adcs_mag.append(Y.FloatParameter(
        system=service,
        name=f"ADCS_MAG_{c}",
        encoding=Y.float32le_t,
    ))

adcs_sun = Y.IntegerParameter(
    system=service,
    name="ADCS_SUN",
    encoding=Y.int32_t,
)

adcs_mag_telemetry = Y.Container(
    system=service,
    base="/PUS/pus-tm",
    name="ADCSMagTelemetry",
    condition=Y.AndExpression(
        Y.EqExpression("/PUS/pus-tm/type", service_type_id),
        Y.EqExpression("/PUS/pus-tm/subtype", 0),
    ),
    entries=list(map(Y.ParameterEntry, adcs_mag)),
)

adcs_gyro_telemetry = Y.Container(
    system=service,
    base="/PUS/pus-tm",
    name="ADCSGyroTelemetry",
    condition=Y.AndExpression(
        Y.EqExpression("/PUS/pus-tm/type", service_type_id),
        Y.EqExpression("/PUS/pus-tm/subtype", 1),
    ),
    entries=list(map(Y.ParameterEntry, adcs_gyro)),
)

adcs_sun_telemetry = Y.Container(
    system=service,
    base="/PUS/pus-tm",
    name="ADCSSunTelemetry",
    condition=Y.AndExpression(
        Y.EqExpression("/PUS/pus-tm/type", service_type_id),
        Y.EqExpression("/PUS/pus-tm/subtype", 2),
    ),
    entries=[
        Y.ParameterEntry(adcs_sun),
    ],
)

print(service.dumps())

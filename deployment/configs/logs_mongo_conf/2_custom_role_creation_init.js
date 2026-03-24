db.createRole({
    role: "appendOnly",
    privileges: [
      {
        resource: { db: "honeysat_log", collection: "" },
        actions: ["insert"]
      }
    ],
    roles: []
  })
  
db.createUser(
    {
        user: "honeysat_user",
        pwd: "h0n4yS4tt",
        roles: [ 
            { 
                role: "appendOnly",
                db: "honeysat_log"
            }
        ]
    }
);
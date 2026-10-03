/**
 * Virtual Factory - Node-RED learner sandbox (optional, compose profile "sandbox").
 *
 * Local development only: no admin authentication (secure profile: editor login), no HTTPS. Do not expose
 * port 1880 beyond localhost.
 *
 * Mounted read-only at /vf/settings.js (passed with --settings). The editable flow file lives in the named
 * volume "vf_nodered-data" at /data/flows.json; it is seeded once from infra/nodered/flows.json
 * (see the nodered service in infra/docker-compose.yml).
 */
module.exports = {
    uiPort: 1880,
    userDir: "/data",
    flowFile: "flows.json",
    flowFilePretty: true,

    // The example flows hold no credentials (the broker is anonymous). `false` stores credentials unencrypted
    // and stops Node-RED from generating a key and warning about it. Not for production use.
    credentialSecret: false,

    // Open profile: no adminAuth - anyone who can reach localhost:1880 can edit and deploy flows (sandbox only).
    // Secure profile (ADR-0027): editor login with VF_NODERED_ADMIN_USER / VF_NODERED_ADMIN_HASH (bcrypt).
    adminAuth: process.env.VF_NODERED_ADMIN_HASH ? {
        type: "credentials",
        users: [{ username: process.env.VF_NODERED_ADMIN_USER || "admin",
                  password: process.env.VF_NODERED_ADMIN_HASH, permissions: "*" }],
    } : undefined,

    httpRequestTimeout: 30000,          // ms; AAS operations wait up to clientTimeoutDuration (15 s)
    mqttReconnectTime: 5000,
    debugMaxLength: 2000,

    diagnostics: { enabled: true, ui: true },
    runtimeState: { enabled: false, ui: false },
    telemetry: { enabled: false, updateNotification: false },   // offline friendly, no consent prompt

    logging: {
        console: { level: "info", metrics: false, audit: false },
    },

    // Only core nodes are used by the examples; the palette manager stays available for own experiments
    // (installed modules end up in the named volume, needs internet access).
    externalModules: {},

    editorTheme: {
        page: { title: "Virtual Factory - Node-RED sandbox" },
        header: { title: "Virtual Factory sandbox" },
        codeEditor: { lib: "monaco" },
        tours: false,
    },

    functionExternalModules: false,
    functionTimeout: 0,
    functionGlobalContext: {},
    exportGlobalContextKeys: false,
};

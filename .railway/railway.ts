import { defineRailway, project, service, volume } from "railway/iac";

export const partial = "cleartrace-web";

export default defineRailway(() => {
  const cleartraceWebVolume = volume("cleartrace-web-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "asia-southeast1-eqsg3a", sizeMB: 500 });
  const cleartraceWeb = service("cleartrace-web", {
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    start: "/app/docker-entrypoint.sh python3 server.py",
    healthcheck: "/health",
    healthcheckTimeout: 60,
    replicas: { "asia-southeast1-eqsg3a": 1 },
    volumeMounts: { "/data": cleartraceWebVolume },
  });

  return project("cleartrace", {
    variables: { managed: false },
    resources: [cleartraceWeb, cleartraceWebVolume],
  });
});

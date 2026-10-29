# millefeuille

![Version: 0.27.3](https://img.shields.io/badge/Version-0.27.3-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 0.30.3](https://img.shields.io/badge/AppVersion-0.30.3-informational?style=flat-square)

A Helm chart to deploy millefeuille.

## Requirements

Kubernetes: `>=1.25.0-0`

| Repository | Name | Version |
|------------|------|---------|
| https://cloudnative-pg.github.io/charts | cnpg(cluster) | 0.8.1 |
| https://qdrant.github.io/qdrant-helm | qdrant(qdrant) | 1.19.2 |
| oci://registry-1.docker.io/cloudpirates | redis(redis) | 0.27.9 |

## Values

### General

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| commonLabels | object | `{}` | Add labels to all the deployed resources |
| cronjobs | object | `{}` | Map of CronJobs to create (e.g. periodic archiving, cleanup, reports...). Each key is used as the cronjob name and as its `app.kubernetes.io/component` label. Every entry accepts the same fields as a `jobs` entry (see above, minus `hook`) plus the scheduling fields documented in the commented example below. |
| enabled | bool | `true` | Master switch for the whole chart. When `false`, every template renders nothing - use this to keep a release/namespace registered with a deployment system (e.g. an ArgoCD Application that always gets generated for every app/env combination) without actually deploying any resource into it. Note this does NOT cover subchart dependencies added via `Chart.yaml` (e.g. a bundled database/cache) - those still need their own `enabled: false` alongside this one. |
| extraObjects | object | `{}` | Map of extra specs to dynamically add to this chart. Each key is a unique, arbitrary name for the object (only used so `-f` values files/overrides can add, override or remove a single entry by key instead of the whole list - lists don't merge across values files in Helm). |
| fullnameOverride | string | `""` | String to fully override the default application name. |
| jobs | object | `{"migration":{"activeDeadlineSeconds":null,"affinity":{},"args":["alembic","upgrade","head"],"backoffLimit":3,"command":[],"completions":null,"env":{},"envCm":{},"envFrom":[],"envSecret":{},"extraContainers":[],"extraVolumeMounts":[],"extraVolumes":[],"hook":{"deletePolicy":"before-hook-creation,hook-succeeded","enabled":true,"types":["pre-install","pre-upgrade"],"weight":0},"hostAliases":[],"image":{"digest":"","pullPolicy":"IfNotPresent","registry":"ghcr.io","repository":"ia-generative/mille-feuille/backend","tag":""},"imagePullSecrets":[],"initContainers":[],"nodeSelector":{},"parallelism":1,"podAnnotations":{},"podLabels":{},"podSecurityContext":{"fsGroup":1000,"fsGroupChangePolicy":"OnRootMismatch","runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000,"seccompProfile":{"type":"RuntimeDefault"}},"resources":{"limits":{"cpu":"500m","memory":"512Mi"},"requests":{"cpu":"100m","memory":"128Mi"}},"restartPolicy":"Never","securityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"privileged":false,"readOnlyRootFilesystem":true,"runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000},"serviceAccount":{"annotations":{},"automountServiceAccountToken":false,"create":false,"enabled":false,"name":""},"tolerations":[],"ttlSecondsAfterFinished":300,"volumeMounts":[{"mountPath":"/tmp","name":"tmp"}],"volumes":[{"emptyDir":{},"name":"tmp"}]}}` | Map of Jobs to create (e.g. one-off DB migrations, data seeding, archiving...). Each key is used as the job name and as its `app.kubernetes.io/component` label. Every entry accepts the fields documented in the commented example below. |
| nameOverride | string | `""` | Provide a name in place of the default application name. |

### Global

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| global.env | object | `{}` | Map or array of environment variables to inject into all containers (`valueFrom` supported). |
| global.envCm | object | `{}` | Map of environment variables to inject into a configmap loaded by all containers (`valueFrom` not supported). |
| global.envFrom | list | `[]` | List or map of `configMapRef`/`secretRef` entries to load into every container's `envFrom` (merged with each component's own `envFrom`, global entries first). |
| global.envSecret | object | `{}` | Map of environment variables to inject into a secret loaded by all containers (`valueFrom` not supported). |
| global.httpRoute.annotations | object | `{}` | Additional HTTPRoute annotations. |
| global.httpRoute.enabled | bool | `false` | Whether or not the chart-level HTTPRoute should be enabled. |
| global.httpRoute.hostnames | list | `[]` | Hostnames for the HTTPRoute to match. |
| global.httpRoute.labels | object | `{}` | Additional HTTPRoute labels. |
| global.httpRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the HTTPRoute to. |
| global.httpRoute.rules | list | `[]` | Routing rules for the HTTPRoute. Required when `enabled` is true, and every `backendRefs` entry must carry a `name`. |
| global.imagePullSecrets | list | `[]` | Image credentials applied to every component in addition to any component-specific `imagePullSecrets`. |
| global.imageRegistry | string | `""` | Global Docker image registry |
| global.ingress.annotations | object | `{}` | Additional ingress annotations. |
| global.ingress.className | string | `""` | Defines which ingress controller will implement the resource. |
| global.ingress.enabled | bool | `false` | Whether or not the chart-level ingress should be enabled. |
| global.ingress.hosts | list | `[]` | Hosts and paths served by the chart-level ingress. Each path's `backend.serviceName` is required (see above); `backend.portNumber` defaults to 80. |
| global.ingress.labels | object | `{}` | Additional ingress labels. |
| global.ingress.tls | list | `[]` | TLS configuration for the chart-level ingress. |
| global.projectName | string | `""` | Project (e.g. a Harbor project) prepended to the `repository` of every image: set it once here and write `repository: "mille-feuille-backend"` instead of `"<project>/mille-feuille-backend"` in each component. Empty (default): repositories are used as written. A repository that already starts with `<projectName>/` is not prefixed twice. |

### Backend

#### General

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backend.affinity | object | `{}` | Affinity used for app pod. |
| backend.args | list | `[]` | Backend container command args. |
| backend.automountServiceAccountToken | bool | `false` | Mount the ServiceAccount token into the app pods. Defaults to false so a compromised container holds no API credentials; the API server does not need the token unless the app actually talks to the Kubernetes API. Applied at pod level so it holds even when `serviceAccount.name` points at an SA that automounts. |
| backend.command | list | `[]` | Backend container command. |
| backend.containerPort | int | `8080` | Backend container port number. Set to `null`/`0` (and disable `service`/probes) for components that don't listen on any port (e.g. a queue consumer). |
| backend.containerPortName | string | `"http"` | Backend container port name. |
| backend.deploymentType | string | `"Deployment"` | Workload kind to deploy the app as. One of "Deployment", "StatefulSet" or "DaemonSet" (validated at render time - an unknown value fails instead of producing a release with no workload). Use the top-level `jobs` / `cronjobs` maps for one-off or scheduled workloads. Some values only apply to certain kinds: `replicaCount`/`autoscaling` and `strategy` are Deployment-only (`autoscaling` also works on a StatefulSet), `volumeClaims`/`extraVolumeClaims` are StatefulSet-only, and `updateStrategy` covers StatefulSet and DaemonSet. |
| backend.dnsConfig | object | `{}` | Pod DNS configuration, merged with `dnsPolicy` by the kubelet. |
| backend.dnsPolicy | string | `""` (`ClusterFirstWithHostNet` when `hostNetwork` is true) | Pod DNS policy. Left empty, it defaults to `ClusterFirstWithHostNet` when `hostNetwork` is true (otherwise a hostNetwork pod silently stops resolving cluster DNS) and to the Kubernetes default `ClusterFirst` when it isn't. |
| backend.enableServiceLinks | bool | `false` | Inject the legacy `{SVC}_SERVICE_HOST`/`_PORT` environment variables for every Service in the namespace. Defaults to false: the variables are rarely used, leak the namespace's topology into every container, and can collide with the app's own configuration. Set to true only for an app that genuinely reads them. |
| backend.env | object | `{}` | Map or array of environment variables to inject into the app container (`valueFrom` supported). |
| backend.envCm | object | `{}` | Map of environment variables to inject into a configmap loaded by the app container (`valueFrom` not supported). |
| backend.envFrom | list | `[]` | Backend container env variables loaded from configmap or secret reference. List or map (merged with `global.envFrom` above, global entries first); see `global.envFrom` for both forms. |
| backend.envSecret | object | `{}` | Map of environment variables to inject into a secret loaded by the app container (`valueFrom` not supported). Values placed here are stored in plain text in the values file AND in the Helm release secret, so use it for non-sensitive-but-secret-shaped config only. For real credentials prefer referencing a Secret you manage elsewhere via `envFrom`, or have an operator materialise it (see the `VaultStaticSecret` example under `extraObjects`). |
| backend.extraContainers | list | `[]` | Extra containers to add to the app pod as sidecars. |
| backend.extraPorts | list | `[]` | Backend extra container ports. |
| backend.extraVolumeClaims | list | `[]` | Additional volumeClaims to add, concatenated with `volumeClaims` above at render time. |
| backend.extraVolumeMounts | list | `[]` | Additional volumeMounts to add, concatenated with `volumeMounts` above at render time. |
| backend.extraVolumes | list | `[]` | Additional volumes to add, concatenated with `volumes` above at render time (e.g. to mount a cert or config from a values override without repeating the chart's own volumes). |
| backend.hostAliases | list | `[]` | Host aliases that will be injected at pod-level into /etc/hosts. |
| backend.hostNetwork | bool | `false` | Share the host network namespace. Container ports then bind directly on the node, so they must not collide with anything else running there. |
| backend.hostPID | bool | `false` | Share the host PID namespace (lets the container see and signal host processes). |
| backend.imagePullSecrets | list | `[]` | Image credentials configuration. |
| backend.initContainers | list | `[]` | Init containers to add to the app pod. |
| backend.nodeSelector | object | `{}` | Default node selector for app. |
| backend.podAnnotations | object | `{}` | Annotations for the app deployed pods. |
| backend.podLabels | object | `{}` | Labels for the app deployed pods. |
| backend.podSecurityContext | object | `{"fsGroup":1000,"fsGroupChangePolicy":"OnRootMismatch","runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000,"seccompProfile":{"type":"RuntimeDefault"}}` | Pod-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard. Rendered via `toYaml`, so any `PodSecurityContext` field is accepted. Adjust the UID/GID to whatever your image actually ships with - `runAsNonRoot` makes the kubelet refuse to start a container that would run as root, which is the intended failure mode rather than something to switch off. Set to `null` to omit the block entirely. |
| backend.priorityClassName | string | `""` | PriorityClass to schedule the pods with (e.g. `system-node-critical` for a node agent that must not be evicted under pressure). |
| backend.replicaCount | int | `1` | The number of application controller pods to run. Ignored when `deploymentType` is "DaemonSet" (one pod per node) or when `autoscaling.enabled` is true. |
| backend.revisionHistoryLimit | int | `10` | Revision history limit for the app. |
| backend.securityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"privileged":false,"readOnlyRootFilesystem":true,"runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000}` | Container-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard: no privilege escalation, no capabilities, immutable root filesystem. Rendered via `toYaml`, so any `SecurityContext` field is accepted. Note `readOnlyRootFilesystem` requires the app to write only to mounted volumes - the default `volumes`/`volumeMounts` below provide an `emptyDir` on /tmp for that reason. Set to `null` to omit the block entirely. |
| backend.terminationGracePeriodSeconds | int | `null` (Kubernetes default of 30) | Grace period, in seconds, given to the pod to shut down cleanly before it is killed. |
| backend.tolerations | list | `[]` | Default tolerations for app. |
| backend.topologySpreadConstraints | list | `[]` | Topology spread constraints used to spread the pods across failure domains. |
| backend.updateStrategy | object | `{}` | Update strategy applied when `deploymentType` is "StatefulSet" or "DaemonSet" (ignored for a Deployment, which uses `strategy` above). Rendered verbatim via `toYaml`, so it takes the native `StatefulSetUpdateStrategy`/`DaemonSetUpdateStrategy` shape of the selected kind; left empty, Kubernetes applies its own default (`RollingUpdate` for both). |
| backend.volumeClaims | list | `[]` | List of volumeClaims to add, rendered as the StatefulSet's `volumeClaimTemplates`. Requires `deploymentType: "StatefulSet"` - setting it on a Deployment or DaemonSet fails at render time rather than being silently dropped (use `volumes`/`extraVolumes` there instead). |
| backend.volumeMounts | list | `[{"mountPath":"/tmp","name":"tmp"}]` | List of mounts to add (normally used with `volumes` or `volumeClaims`). Prefer this for mounts the chart itself always needs; use `extraVolumeMounts` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to the `/tmp` mount backing the hardened `readOnlyRootFilesystem` default (see `volumes` above). |
| backend.volumes | list | `[{"emptyDir":{},"name":"tmp"}]` | List of volumes to add. Prefer this for volumes the chart itself always needs (e.g. security-hardening `emptyDir`s); use `extraVolumes` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to a `/tmp` `emptyDir`, which is what makes the default `securityContext.readOnlyRootFilesystem: true` usable - drop it only if you also relax that. Helm replaces lists wholesale rather than merging them, so overriding this key means restating the entries you want to keep. |

#### Autoscaling

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backend.autoscaling.enabled | bool | `false` | Enable Horizontal Pod Autoscaler for the app. |
| backend.autoscaling.maxReplicas | int | `3` | Maximum number of replicas for the app. |
| backend.autoscaling.minReplicas | int | `1` | Minimum number of replicas for the app. |
| backend.autoscaling.targetCPUUtilizationPercentage | int | `80` | Average CPU utilization percentage for the app. |
| backend.autoscaling.targetMemoryUtilizationPercentage | int | `80` | Average memory utilization percentage for the app. |

#### GrpcRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backend.grpcRoute.annotations | object | `{}` | Additional GRPCRoute annotations. |
| backend.grpcRoute.enabled | bool | `false` | Enable a GRPCRoute resource for this service. |
| backend.grpcRoute.hostnames | list | `[]` | Hostnames for the GRPCRoute to match. |
| backend.grpcRoute.labels | object | `{}` | Additional GRPCRoute labels. |
| backend.grpcRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the GRPCRoute to. |
| backend.grpcRoute.rules | list | `[]` | Routing rules for the GRPCRoute. |

#### HttpRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backend.httpRoute.annotations | object | `{}` | Additional HTTPRoute annotations. |
| backend.httpRoute.enabled | bool | `false` | Enable an HTTPRoute resource for this service. |
| backend.httpRoute.hostnames | list | `[]` | Hostnames for the HTTPRoute to match. |
| backend.httpRoute.labels | object | `{}` | Additional HTTPRoute labels. |
| backend.httpRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the HTTPRoute to. |
| backend.httpRoute.rules | list | `[]` | Routing rules for the HTTPRoute. |

#### Image

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backend.image.digest | string | `""` | Image digest (`sha256:...`). When set it takes precedence over `tag`, pinning the exact image content so the same release can never resolve to a different build - preferred over a mutable tag for anything you deploy to production. |
| backend.image.pullPolicy | string | `"IfNotPresent"` | Image pull policy for the app. |
| backend.image.registry | string | `"ghcr.io"` | Registry to use for the app. |
| backend.image.repository | string | `"ia-generative/mille-feuille/backend"` | Repository to use for the app. |
| backend.image.tag | string | `""` | Tag to use for the app. Overrides the image tag whose default is the chart appVersion. |

#### Ingress

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backend.ingress.annotations | object | `{}` | Additional ingress annotations. |
| backend.ingress.className | string | `""` | Defines which ingress controller will implement the resource. |
| backend.ingress.enabled | bool | `false` | Whether or not ingress should be enabled. |
| backend.ingress.hosts[0].name | string | `"domain.local"` | Name of the host record. |
| backend.ingress.hosts[0].paths | list | `[{"backend":{"portNumber":null,"serviceName":""},"path":"/","pathType":"Prefix"}]` | Paths of the host record to manage routing (avoids repeating the same host for multiple paths/backends). |
| backend.ingress.hosts[0].paths[0].backend.portNumber | string | `nil` | Port used by the backend service linked to the path (leave null to use the app service port). |
| backend.ingress.hosts[0].paths[0].backend.serviceName | string | `""` | Name of the backend service linked to the path (leave empty to use the app service). |
| backend.ingress.hosts[0].paths[0].path | string | `"/"` | Path of the host record to manage routing. |
| backend.ingress.hosts[0].paths[0].pathType | string | `"Prefix"` | Path type of the host record. |
| backend.ingress.labels | object | `{}` | Additional ingress labels. |
| backend.ingress.tls | list | `[]` | Enable TLS configuration. |

#### Metrics

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backend.metrics.enabled | bool | `false` | Deploy metrics service. |
| backend.metrics.service.annotations | object | `{}` | Metrics service annotations. |
| backend.metrics.service.labels | object | `{}` | Metrics service labels. |
| backend.metrics.service.port | int | `9000` | Metrics service port. |
| backend.metrics.service.portName | string | `"metrics"` | Metrics service port name. |
| backend.metrics.service.targetPort | int | `9000` | Metrics service target port. |
| backend.metrics.service.type | string | `"ClusterIP"` | Type of metrics service to create. |
| backend.metrics.serviceMonitor.annotations | object | `{}` | Prometheus ServiceMonitor annotations. |
| backend.metrics.serviceMonitor.enabled | bool | `false` | Enable a prometheus ServiceMonitor. |
| backend.metrics.serviceMonitor.endpoints[0].basicAuth.password | string | `""` | The secret in the service monitor namespace that contains the password for authentication. |
| backend.metrics.serviceMonitor.endpoints[0].basicAuth.username | string | `""` | The secret in the service monitor namespace that contains the username for authentication. |
| backend.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.key | string | `""` | Secret key to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| backend.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.name | string | `""` | Secret name to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| backend.metrics.serviceMonitor.endpoints[0].honorLabels | bool | `false` | When true, honorLabels preserves the metric’s labels when they collide with the target’s labels. |
| backend.metrics.serviceMonitor.endpoints[0].interval | string | `"30s"` | Prometheus ServiceMonitor interval. |
| backend.metrics.serviceMonitor.endpoints[0].metricRelabelings | list | `[]` | Prometheus MetricRelabelConfigs to apply to samples before ingestion. |
| backend.metrics.serviceMonitor.endpoints[0].path | string | `"/metrics"` | Path used by the Prometheus ServiceMonitor to scrape metrics. |
| backend.metrics.serviceMonitor.endpoints[0].relabelings | list | `[]` | Prometheus RelabelConfigs to apply to samples before scraping. |
| backend.metrics.serviceMonitor.endpoints[0].scheme | string | `""` | Prometheus ServiceMonitor scheme. |
| backend.metrics.serviceMonitor.endpoints[0].scrapeTimeout | string | `"10s"` | Prometheus ServiceMonitor scrapeTimeout. If empty, Prometheus uses the global scrape timeout unless it is less than the target's scrape interval value in which the latter is used. |
| backend.metrics.serviceMonitor.endpoints[0].selector | object | `{}` | Prometheus ServiceMonitor selector. |
| backend.metrics.serviceMonitor.endpoints[0].tlsConfig | object | `{}` | Prometheus ServiceMonitor tlsConfig. |
| backend.metrics.serviceMonitor.labels | object | `{}` | Prometheus ServiceMonitor labels. |

#### NetworkPolicy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backend.networkPolicy.annotations | object | `{}` | Annotations to be added to the app NetworkPolicy. |
| backend.networkPolicy.create | bool | `false` | Create NetworkPolicy object for the app. The policy always selects this component's pods only (via its selector labels), never the whole namespace. |
| backend.networkPolicy.egress | list | `[]` | Egress rules for the NetworkPolicy object. |
| backend.networkPolicy.ingress | list | `[]` | Ingress rules for the NetworkPolicy object. |
| backend.networkPolicy.labels | object | `{}` | Labels to be added to the app NetworkPolicy. |
| backend.networkPolicy.policyTypes | list | `["Ingress"]` | Policy types used in the NetworkPolicy object. |

#### Pdb

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backend.pdb.annotations | object | `{}` | Annotations to be added to app pdb. |
| backend.pdb.enabled | bool | `false` | Deploy a PodDisruptionBudget for the app |
| backend.pdb.labels | object | `{}` | Labels to be added to app pdb. |
| backend.pdb.maxUnavailable | string | `""` | Number of pods that are unavailable after eviction as number or percentage (eg.: 50%). Has higher precedence over `backend.pdb.minAvailable`. |
| backend.pdb.minAvailable | string | `""` | Number of pods that are available after eviction as number or percentage (eg.: 50%). One of `minAvailable` / `maxUnavailable` must be set when `pdb.enabled` is true - a budget of 0 is the same as having no budget at all, so leaving both empty fails at render time. |

#### Probes

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backend.probes.livenessProbe.failureThreshold | int | `3` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| backend.probes.livenessProbe.httpGet.path | string | `"/"` | Backend container healthcheck endpoint (livenessProbe is defined using `toYaml` so it is possible to override it completely). |
| backend.probes.livenessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| backend.probes.livenessProbe.initialDelaySeconds | int | `30` | Number of seconds after the container has started before probe is initiated. |
| backend.probes.livenessProbe.periodSeconds | int | `30` | How often (in seconds) to perform the probe. |
| backend.probes.livenessProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| backend.probes.livenessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| backend.probes.readinessProbe.failureThreshold | int | `2` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| backend.probes.readinessProbe.httpGet.path | string | `"/"` | Backend container healthcheck endpoint (readinessProbe is defined using `toYaml` so it is possible to override it completely). |
| backend.probes.readinessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| backend.probes.readinessProbe.initialDelaySeconds | int | `10` | Number of seconds after the container has started before probe is initiated. |
| backend.probes.readinessProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| backend.probes.readinessProbe.successThreshold | int | `2` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| backend.probes.readinessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| backend.probes.startupProbe.failureThreshold | int | `10` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| backend.probes.startupProbe.httpGet.path | string | `"/"` | Backend container healthcheck endpoint (startupProbe is defined using `toYaml` so it is possible to override it completely). |
| backend.probes.startupProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| backend.probes.startupProbe.initialDelaySeconds | int | `0` | Number of seconds after the container has started before probe is initiated. |
| backend.probes.startupProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| backend.probes.startupProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| backend.probes.startupProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |

#### Resources

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backend.resources.limits.cpu | string | `"500m"` | CPU limit for the app. |
| backend.resources.limits.memory | string | `"2Gi"` | Memory limit for the app. |
| backend.resources.requests.cpu | string | `"100m"` | CPU request for the app. |
| backend.resources.requests.memory | string | `"256Mi"` | Memory request for the app. |

#### Service

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backend.service.enabled | bool | `true` | Whether or not to create a Service for the app. Set to `false` for components that don't accept traffic (e.g. a queue consumer with no `containerPort`). |
| backend.service.extraPorts | list | `[]` | Extra service ports. |
| backend.service.nodePort | int | `null` (allocated by Kubernetes) | Port used when type is `NodePort` to expose the service on the given node port. Left empty, Kubernetes allocates one from the configured node-port range, which avoids two releases of this chart colliding on the same hardcoded port. |
| backend.service.port | int | `80` | Port used by the service. |
| backend.service.portName | string | `"http"` | Port name used by the service. |
| backend.service.protocol | string | `"TCP"` | Protocol used by the service. |
| backend.service.type | string | `"ClusterIP"` | Type of service to create for the app. |

#### ServiceAccount

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backend.serviceAccount.annotations | object | `{}` | Annotations applied to created service account. |
| backend.serviceAccount.automountServiceAccountToken | bool | `false` | Should the service account access token be automount in the pod. |
| backend.serviceAccount.clusterRole.create | bool | `false` | Should the clusterRole be created. |
| backend.serviceAccount.clusterRole.rules | list | `[]` | ClusterRole rules associated with the service account. |
| backend.serviceAccount.create | bool | `false` | Create a service account. |
| backend.serviceAccount.enabled | bool | `false` | Enable the service account. |
| backend.serviceAccount.name | string | `""` | Service account name. |
| backend.serviceAccount.role.create | bool | `false` | Should the role be created. |
| backend.serviceAccount.role.rules | list | `[]` | Role rules associated with the service account. |

#### Strategy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backend.strategy.rollingUpdate.maxSurge | int | `1` | The maximum number of pods that can be scheduled above the desired number of pods. |
| backend.strategy.rollingUpdate.maxUnavailable | int | `1` | The maximum number of pods that can be unavailable during the update process. |
| backend.strategy.type | string | `"RollingUpdate"` | Strategy type used to replace old Pods by new ones, can be `Recreate` or `RollingUpdate`. Only applied when `deploymentType` is "Deployment". |

### EphemeralFrontend

#### General

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| ephemeral_frontend.affinity | object | `{}` | Affinity used for app pod. |
| ephemeral_frontend.args | list | `[]` | Ephemeral frontend container command args. |
| ephemeral_frontend.automountServiceAccountToken | bool | `false` | Mount the ServiceAccount token into the app pods. Defaults to false so a compromised container holds no API credentials; the API server does not need the token unless the app actually talks to the Kubernetes API. Applied at pod level so it holds even when `serviceAccount.name` points at an SA that automounts. |
| ephemeral_frontend.command | list | `[]` | Ephemeral frontend container command. |
| ephemeral_frontend.containerPort | int | `8080` | Ephemeral frontend container port number. Set to `null`/`0` (and disable `service`/probes) for components that don't listen on any port (e.g. a queue consumer). |
| ephemeral_frontend.containerPortName | string | `"http"` | Ephemeral frontend container port name. |
| ephemeral_frontend.deploymentType | string | `"Deployment"` | Workload kind to deploy the app as. One of "Deployment", "StatefulSet" or "DaemonSet" (validated at render time - an unknown value fails instead of producing a release with no workload). Use the top-level `jobs` / `cronjobs` maps for one-off or scheduled workloads. Some values only apply to certain kinds: `replicaCount`/`autoscaling` and `strategy` are Deployment-only (`autoscaling` also works on a StatefulSet), `volumeClaims`/`extraVolumeClaims` are StatefulSet-only, and `updateStrategy` covers StatefulSet and DaemonSet. |
| ephemeral_frontend.dnsConfig | object | `{}` | Pod DNS configuration, merged with `dnsPolicy` by the kubelet. |
| ephemeral_frontend.dnsPolicy | string | `""` (`ClusterFirstWithHostNet` when `hostNetwork` is true) | Pod DNS policy. Left empty, it defaults to `ClusterFirstWithHostNet` when `hostNetwork` is true (otherwise a hostNetwork pod silently stops resolving cluster DNS) and to the Kubernetes default `ClusterFirst` when it isn't. |
| ephemeral_frontend.enableServiceLinks | bool | `false` | Inject the legacy `{SVC}_SERVICE_HOST`/`_PORT` environment variables for every Service in the namespace. Defaults to false: the variables are rarely used, leak the namespace's topology into every container, and can collide with the app's own configuration. Set to true only for an app that genuinely reads them. |
| ephemeral_frontend.env | object | `{}` | Map or array of environment variables to inject into the app container (`valueFrom` supported). |
| ephemeral_frontend.envCm | object | `{}` | Map of environment variables to inject into a configmap loaded by the app container (`valueFrom` not supported). |
| ephemeral_frontend.envFrom | list | `[]` | Ephemeral frontend container env variables loaded from configmap or secret reference. List or map (merged with `global.envFrom` above, global entries first); see `global.envFrom` for both forms. |
| ephemeral_frontend.envSecret | object | `{}` | Map of environment variables to inject into a secret loaded by the app container (`valueFrom` not supported). Values placed here are stored in plain text in the values file AND in the Helm release secret, so use it for non-sensitive-but-secret-shaped config only. For real credentials prefer referencing a Secret you manage elsewhere via `envFrom`, or have an operator materialise it (see the `VaultStaticSecret` example under `extraObjects`). |
| ephemeral_frontend.extraContainers | list | `[]` | Extra containers to add to the app pod as sidecars. |
| ephemeral_frontend.extraPorts | list | `[]` | Ephemeral frontend extra container ports. |
| ephemeral_frontend.extraVolumeClaims | list | `[]` | Additional volumeClaims to add, concatenated with `volumeClaims` above at render time. |
| ephemeral_frontend.extraVolumeMounts | list | `[]` | Additional volumeMounts to add, concatenated with `volumeMounts` above at render time. |
| ephemeral_frontend.extraVolumes | list | `[]` | Additional volumes to add, concatenated with `volumes` above at render time (e.g. to mount a cert or config from a values override without repeating the chart's own volumes). |
| ephemeral_frontend.hostAliases | list | `[]` | Host aliases that will be injected at pod-level into /etc/hosts. |
| ephemeral_frontend.hostNetwork | bool | `false` | Share the host network namespace. Container ports then bind directly on the node, so they must not collide with anything else running there. |
| ephemeral_frontend.hostPID | bool | `false` | Share the host PID namespace (lets the container see and signal host processes). |
| ephemeral_frontend.imagePullSecrets | list | `[]` | Image credentials configuration. |
| ephemeral_frontend.initContainers | list | `[]` | Init containers to add to the app pod. |
| ephemeral_frontend.nodeSelector | object | `{}` | Default node selector for app. |
| ephemeral_frontend.podAnnotations | object | `{}` | Annotations for the app deployed pods. |
| ephemeral_frontend.podLabels | object | `{}` | Labels for the app deployed pods. |
| ephemeral_frontend.podSecurityContext | object | `{"fsGroup":1000,"fsGroupChangePolicy":"OnRootMismatch","runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000,"seccompProfile":{"type":"RuntimeDefault"}}` | Pod-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard. Rendered via `toYaml`, so any `PodSecurityContext` field is accepted. Adjust the UID/GID to whatever your image actually ships with - `runAsNonRoot` makes the kubelet refuse to start a container that would run as root, which is the intended failure mode rather than something to switch off. Set to `null` to omit the block entirely. |
| ephemeral_frontend.priorityClassName | string | `""` | PriorityClass to schedule the pods with (e.g. `system-node-critical` for a node agent that must not be evicted under pressure). |
| ephemeral_frontend.replicaCount | int | `1` | The number of application controller pods to run. Ignored when `deploymentType` is "DaemonSet" (one pod per node) or when `autoscaling.enabled` is true. |
| ephemeral_frontend.revisionHistoryLimit | int | `10` | Revision history limit for the app. |
| ephemeral_frontend.securityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"privileged":false,"readOnlyRootFilesystem":true,"runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000}` | Container-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard: no privilege escalation, no capabilities, immutable root filesystem. Rendered via `toYaml`, so any `SecurityContext` field is accepted. Note `readOnlyRootFilesystem` requires the app to write only to mounted volumes - the default `volumes`/`volumeMounts` below provide an `emptyDir` on /tmp for that reason. Set to `null` to omit the block entirely. |
| ephemeral_frontend.terminationGracePeriodSeconds | int | `null` (Kubernetes default of 30) | Grace period, in seconds, given to the pod to shut down cleanly before it is killed. |
| ephemeral_frontend.tolerations | list | `[]` | Default tolerations for app. |
| ephemeral_frontend.topologySpreadConstraints | list | `[]` | Topology spread constraints used to spread the pods across failure domains. |
| ephemeral_frontend.updateStrategy | object | `{}` | Update strategy applied when `deploymentType` is "StatefulSet" or "DaemonSet" (ignored for a Deployment, which uses `strategy` above). Rendered verbatim via `toYaml`, so it takes the native `StatefulSetUpdateStrategy`/`DaemonSetUpdateStrategy` shape of the selected kind; left empty, Kubernetes applies its own default (`RollingUpdate` for both). |
| ephemeral_frontend.volumeClaims | list | `[]` | List of volumeClaims to add, rendered as the StatefulSet's `volumeClaimTemplates`. Requires `deploymentType: "StatefulSet"` - setting it on a Deployment or DaemonSet fails at render time rather than being silently dropped (use `volumes`/`extraVolumes` there instead). |
| ephemeral_frontend.volumeMounts | list | `[{"mountPath":"/tmp","name":"tmp"}]` | List of mounts to add (normally used with `volumes` or `volumeClaims`). Prefer this for mounts the chart itself always needs; use `extraVolumeMounts` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to the `/tmp` mount backing the hardened `readOnlyRootFilesystem` default (see `volumes` above). |
| ephemeral_frontend.volumes | list | `[{"emptyDir":{},"name":"tmp"}]` | List of volumes to add. Prefer this for volumes the chart itself always needs (e.g. security-hardening `emptyDir`s); use `extraVolumes` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to a `/tmp` `emptyDir`, which is what makes the default `securityContext.readOnlyRootFilesystem: true` usable - drop it only if you also relax that. Helm replaces lists wholesale rather than merging them, so overriding this key means restating the entries you want to keep. |

#### Autoscaling

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| ephemeral_frontend.autoscaling.enabled | bool | `false` | Enable Horizontal Pod Autoscaler for the app. |
| ephemeral_frontend.autoscaling.maxReplicas | int | `3` | Maximum number of replicas for the app. |
| ephemeral_frontend.autoscaling.minReplicas | int | `1` | Minimum number of replicas for the app. |
| ephemeral_frontend.autoscaling.targetCPUUtilizationPercentage | int | `80` | Average CPU utilization percentage for the app. |
| ephemeral_frontend.autoscaling.targetMemoryUtilizationPercentage | int | `80` | Average memory utilization percentage for the app. |

#### GrpcRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| ephemeral_frontend.grpcRoute.annotations | object | `{}` | Additional GRPCRoute annotations. |
| ephemeral_frontend.grpcRoute.enabled | bool | `false` | Enable a GRPCRoute resource for this service. |
| ephemeral_frontend.grpcRoute.hostnames | list | `[]` | Hostnames for the GRPCRoute to match. |
| ephemeral_frontend.grpcRoute.labels | object | `{}` | Additional GRPCRoute labels. |
| ephemeral_frontend.grpcRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the GRPCRoute to. |
| ephemeral_frontend.grpcRoute.rules | list | `[]` | Routing rules for the GRPCRoute. |

#### HttpRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| ephemeral_frontend.httpRoute.annotations | object | `{}` | Additional HTTPRoute annotations. |
| ephemeral_frontend.httpRoute.enabled | bool | `false` | Enable an HTTPRoute resource for this service. |
| ephemeral_frontend.httpRoute.hostnames | list | `[]` | Hostnames for the HTTPRoute to match. |
| ephemeral_frontend.httpRoute.labels | object | `{}` | Additional HTTPRoute labels. |
| ephemeral_frontend.httpRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the HTTPRoute to. |
| ephemeral_frontend.httpRoute.rules | list | `[]` | Routing rules for the HTTPRoute. |

#### Image

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| ephemeral_frontend.image.digest | string | `""` | Image digest (`sha256:...`). When set it takes precedence over `tag`, pinning the exact image content so the same release can never resolve to a different build - preferred over a mutable tag for anything you deploy to production. |
| ephemeral_frontend.image.pullPolicy | string | `"IfNotPresent"` | Image pull policy for the app. |
| ephemeral_frontend.image.registry | string | `"ghcr.io"` | Registry to use for the app. |
| ephemeral_frontend.image.repository | string | `"ia-generative/mille-feuille/ephemeral-frontend"` | Repository to use for the app. |
| ephemeral_frontend.image.tag | string | `""` | Tag to use for the app. Overrides the image tag whose default is the chart appVersion. |

#### Ingress

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| ephemeral_frontend.ingress.annotations | object | `{}` | Additional ingress annotations. |
| ephemeral_frontend.ingress.className | string | `""` | Defines which ingress controller will implement the resource. |
| ephemeral_frontend.ingress.enabled | bool | `false` | Whether or not ingress should be enabled. |
| ephemeral_frontend.ingress.hosts[0].name | string | `"domain.local"` | Name of the host record. |
| ephemeral_frontend.ingress.hosts[0].paths | list | `[{"backend":{"portNumber":null,"serviceName":""},"path":"/","pathType":"Prefix"}]` | Paths of the host record to manage routing (avoids repeating the same host for multiple paths/backends). |
| ephemeral_frontend.ingress.hosts[0].paths[0].backend.portNumber | string | `nil` | Port used by the backend service linked to the path (leave null to use the app service port). |
| ephemeral_frontend.ingress.hosts[0].paths[0].backend.serviceName | string | `""` | Name of the backend service linked to the path (leave empty to use the app service). |
| ephemeral_frontend.ingress.hosts[0].paths[0].path | string | `"/"` | Path of the host record to manage routing. |
| ephemeral_frontend.ingress.hosts[0].paths[0].pathType | string | `"Prefix"` | Path type of the host record. |
| ephemeral_frontend.ingress.labels | object | `{}` | Additional ingress labels. |
| ephemeral_frontend.ingress.tls | list | `[]` | Enable TLS configuration. |

#### Metrics

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| ephemeral_frontend.metrics.enabled | bool | `false` | Deploy metrics service. |
| ephemeral_frontend.metrics.service.annotations | object | `{}` | Metrics service annotations. |
| ephemeral_frontend.metrics.service.labels | object | `{}` | Metrics service labels. |
| ephemeral_frontend.metrics.service.port | int | `9000` | Metrics service port. |
| ephemeral_frontend.metrics.service.portName | string | `"metrics"` | Metrics service port name. |
| ephemeral_frontend.metrics.service.targetPort | int | `9000` | Metrics service target port. |
| ephemeral_frontend.metrics.service.type | string | `"ClusterIP"` | Type of metrics service to create. |
| ephemeral_frontend.metrics.serviceMonitor.annotations | object | `{}` | Prometheus ServiceMonitor annotations. |
| ephemeral_frontend.metrics.serviceMonitor.enabled | bool | `false` | Enable a prometheus ServiceMonitor. |
| ephemeral_frontend.metrics.serviceMonitor.endpoints[0].basicAuth.password | string | `""` | The secret in the service monitor namespace that contains the password for authentication. |
| ephemeral_frontend.metrics.serviceMonitor.endpoints[0].basicAuth.username | string | `""` | The secret in the service monitor namespace that contains the username for authentication. |
| ephemeral_frontend.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.key | string | `""` | Secret key to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| ephemeral_frontend.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.name | string | `""` | Secret name to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| ephemeral_frontend.metrics.serviceMonitor.endpoints[0].honorLabels | bool | `false` | When true, honorLabels preserves the metric’s labels when they collide with the target’s labels. |
| ephemeral_frontend.metrics.serviceMonitor.endpoints[0].interval | string | `"30s"` | Prometheus ServiceMonitor interval. |
| ephemeral_frontend.metrics.serviceMonitor.endpoints[0].metricRelabelings | list | `[]` | Prometheus MetricRelabelConfigs to apply to samples before ingestion. |
| ephemeral_frontend.metrics.serviceMonitor.endpoints[0].path | string | `"/metrics"` | Path used by the Prometheus ServiceMonitor to scrape metrics. |
| ephemeral_frontend.metrics.serviceMonitor.endpoints[0].relabelings | list | `[]` | Prometheus RelabelConfigs to apply to samples before scraping. |
| ephemeral_frontend.metrics.serviceMonitor.endpoints[0].scheme | string | `""` | Prometheus ServiceMonitor scheme. |
| ephemeral_frontend.metrics.serviceMonitor.endpoints[0].scrapeTimeout | string | `"10s"` | Prometheus ServiceMonitor scrapeTimeout. If empty, Prometheus uses the global scrape timeout unless it is less than the target's scrape interval value in which the latter is used. |
| ephemeral_frontend.metrics.serviceMonitor.endpoints[0].selector | object | `{}` | Prometheus ServiceMonitor selector. |
| ephemeral_frontend.metrics.serviceMonitor.endpoints[0].tlsConfig | object | `{}` | Prometheus ServiceMonitor tlsConfig. |
| ephemeral_frontend.metrics.serviceMonitor.labels | object | `{}` | Prometheus ServiceMonitor labels. |

#### NetworkPolicy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| ephemeral_frontend.networkPolicy.annotations | object | `{}` | Annotations to be added to the app NetworkPolicy. |
| ephemeral_frontend.networkPolicy.create | bool | `false` | Create NetworkPolicy object for the app. The policy always selects this component's pods only (via its selector labels), never the whole namespace. |
| ephemeral_frontend.networkPolicy.egress | list | `[]` | Egress rules for the NetworkPolicy object. |
| ephemeral_frontend.networkPolicy.ingress | list | `[]` | Ingress rules for the NetworkPolicy object. |
| ephemeral_frontend.networkPolicy.labels | object | `{}` | Labels to be added to the app NetworkPolicy. |
| ephemeral_frontend.networkPolicy.policyTypes | list | `["Ingress"]` | Policy types used in the NetworkPolicy object. |

#### Pdb

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| ephemeral_frontend.pdb.annotations | object | `{}` | Annotations to be added to app pdb. |
| ephemeral_frontend.pdb.enabled | bool | `false` | Deploy a PodDisruptionBudget for the app |
| ephemeral_frontend.pdb.labels | object | `{}` | Labels to be added to app pdb. |
| ephemeral_frontend.pdb.maxUnavailable | string | `""` | Number of pods that are unavailable after eviction as number or percentage (eg.: 50%). Has higher precedence over `ephemeral_frontend.pdb.minAvailable`. |
| ephemeral_frontend.pdb.minAvailable | string | `""` | Number of pods that are available after eviction as number or percentage (eg.: 50%). One of `minAvailable` / `maxUnavailable` must be set when `pdb.enabled` is true - a budget of 0 is the same as having no budget at all, so leaving both empty fails at render time. |

#### Probes

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| ephemeral_frontend.probes.livenessProbe.failureThreshold | int | `3` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| ephemeral_frontend.probes.livenessProbe.httpGet.path | string | `"/"` | Ephemeral frontend container healthcheck endpoint (livenessProbe is defined using `toYaml` so it is possible to override it completely). |
| ephemeral_frontend.probes.livenessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| ephemeral_frontend.probes.livenessProbe.initialDelaySeconds | int | `30` | Number of seconds after the container has started before probe is initiated. |
| ephemeral_frontend.probes.livenessProbe.periodSeconds | int | `30` | How often (in seconds) to perform the probe. |
| ephemeral_frontend.probes.livenessProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| ephemeral_frontend.probes.livenessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| ephemeral_frontend.probes.readinessProbe.failureThreshold | int | `2` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| ephemeral_frontend.probes.readinessProbe.httpGet.path | string | `"/"` | Ephemeral frontend container healthcheck endpoint (readinessProbe is defined using `toYaml` so it is possible to override it completely). |
| ephemeral_frontend.probes.readinessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| ephemeral_frontend.probes.readinessProbe.initialDelaySeconds | int | `10` | Number of seconds after the container has started before probe is initiated. |
| ephemeral_frontend.probes.readinessProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| ephemeral_frontend.probes.readinessProbe.successThreshold | int | `2` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| ephemeral_frontend.probes.readinessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| ephemeral_frontend.probes.startupProbe.failureThreshold | int | `10` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| ephemeral_frontend.probes.startupProbe.httpGet.path | string | `"/"` | Ephemeral frontend container healthcheck endpoint (startupProbe is defined using `toYaml` so it is possible to override it completely). |
| ephemeral_frontend.probes.startupProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| ephemeral_frontend.probes.startupProbe.initialDelaySeconds | int | `0` | Number of seconds after the container has started before probe is initiated. |
| ephemeral_frontend.probes.startupProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| ephemeral_frontend.probes.startupProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| ephemeral_frontend.probes.startupProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |

#### Resources

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| ephemeral_frontend.resources.limits.cpu | string | `"500m"` | CPU limit for the app. |
| ephemeral_frontend.resources.limits.memory | string | `"2Gi"` | Memory limit for the app. |
| ephemeral_frontend.resources.requests.cpu | string | `"100m"` | CPU request for the app. |
| ephemeral_frontend.resources.requests.memory | string | `"256Mi"` | Memory request for the app. |

#### Service

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| ephemeral_frontend.service.enabled | bool | `true` | Whether or not to create a Service for the app. Set to `false` for components that don't accept traffic (e.g. a queue consumer with no `containerPort`). |
| ephemeral_frontend.service.extraPorts | list | `[]` | Extra service ports. |
| ephemeral_frontend.service.nodePort | int | `null` (allocated by Kubernetes) | Port used when type is `NodePort` to expose the service on the given node port. Left empty, Kubernetes allocates one from the configured node-port range, which avoids two releases of this chart colliding on the same hardcoded port. |
| ephemeral_frontend.service.port | int | `80` | Port used by the service. |
| ephemeral_frontend.service.portName | string | `"http"` | Port name used by the service. |
| ephemeral_frontend.service.protocol | string | `"TCP"` | Protocol used by the service. |
| ephemeral_frontend.service.type | string | `"ClusterIP"` | Type of service to create for the app. |

#### ServiceAccount

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| ephemeral_frontend.serviceAccount.annotations | object | `{}` | Annotations applied to created service account. |
| ephemeral_frontend.serviceAccount.automountServiceAccountToken | bool | `false` | Should the service account access token be automount in the pod. |
| ephemeral_frontend.serviceAccount.clusterRole.create | bool | `false` | Should the clusterRole be created. |
| ephemeral_frontend.serviceAccount.clusterRole.rules | list | `[]` | ClusterRole rules associated with the service account. |
| ephemeral_frontend.serviceAccount.create | bool | `false` | Create a service account. |
| ephemeral_frontend.serviceAccount.enabled | bool | `false` | Enable the service account. |
| ephemeral_frontend.serviceAccount.name | string | `""` | Service account name. |
| ephemeral_frontend.serviceAccount.role.create | bool | `false` | Should the role be created. |
| ephemeral_frontend.serviceAccount.role.rules | list | `[]` | Role rules associated with the service account. |

#### Strategy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| ephemeral_frontend.strategy.rollingUpdate.maxSurge | int | `1` | The maximum number of pods that can be scheduled above the desired number of pods. |
| ephemeral_frontend.strategy.rollingUpdate.maxUnavailable | int | `1` | The maximum number of pods that can be unavailable during the update process. |
| ephemeral_frontend.strategy.type | string | `"RollingUpdate"` | Strategy type used to replace old Pods by new ones, can be `Recreate` or `RollingUpdate`. Only applied when `deploymentType` is "Deployment". |

### Frontend

#### General

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| frontend.affinity | object | `{}` | Affinity used for app pod. |
| frontend.args | list | `[]` | Frontend container command args. |
| frontend.automountServiceAccountToken | bool | `false` | Mount the ServiceAccount token into the app pods. Defaults to false so a compromised container holds no API credentials; the API server does not need the token unless the app actually talks to the Kubernetes API. Applied at pod level so it holds even when `serviceAccount.name` points at an SA that automounts. |
| frontend.command | list | `[]` | Frontend container command. |
| frontend.containerPort | int | `8080` | Frontend container port number. Set to `null`/`0` (and disable `service`/probes) for components that don't listen on any port (e.g. a queue consumer). |
| frontend.containerPortName | string | `"http"` | Frontend container port name. |
| frontend.deploymentType | string | `"Deployment"` | Workload kind to deploy the app as. One of "Deployment", "StatefulSet" or "DaemonSet" (validated at render time - an unknown value fails instead of producing a release with no workload). Use the top-level `jobs` / `cronjobs` maps for one-off or scheduled workloads. Some values only apply to certain kinds: `replicaCount`/`autoscaling` and `strategy` are Deployment-only (`autoscaling` also works on a StatefulSet), `volumeClaims`/`extraVolumeClaims` are StatefulSet-only, and `updateStrategy` covers StatefulSet and DaemonSet. |
| frontend.dnsConfig | object | `{}` | Pod DNS configuration, merged with `dnsPolicy` by the kubelet. |
| frontend.dnsPolicy | string | `""` (`ClusterFirstWithHostNet` when `hostNetwork` is true) | Pod DNS policy. Left empty, it defaults to `ClusterFirstWithHostNet` when `hostNetwork` is true (otherwise a hostNetwork pod silently stops resolving cluster DNS) and to the Kubernetes default `ClusterFirst` when it isn't. |
| frontend.enableServiceLinks | bool | `false` | Inject the legacy `{SVC}_SERVICE_HOST`/`_PORT` environment variables for every Service in the namespace. Defaults to false: the variables are rarely used, leak the namespace's topology into every container, and can collide with the app's own configuration. Set to true only for an app that genuinely reads them. |
| frontend.env | object | `{}` | Map or array of environment variables to inject into the app container (`valueFrom` supported). |
| frontend.envCm | object | `{}` | Map of environment variables to inject into a configmap loaded by the app container (`valueFrom` not supported). |
| frontend.envFrom | list | `[]` | Frontend container env variables loaded from configmap or secret reference. List or map (merged with `global.envFrom` above, global entries first); see `global.envFrom` for both forms. |
| frontend.envSecret | object | `{}` | Map of environment variables to inject into a secret loaded by the app container (`valueFrom` not supported). Values placed here are stored in plain text in the values file AND in the Helm release secret, so use it for non-sensitive-but-secret-shaped config only. For real credentials prefer referencing a Secret you manage elsewhere via `envFrom`, or have an operator materialise it (see the `VaultStaticSecret` example under `extraObjects`). |
| frontend.extraContainers | list | `[]` | Extra containers to add to the app pod as sidecars. |
| frontend.extraPorts | list | `[]` | Frontend extra container ports. |
| frontend.extraVolumeClaims | list | `[]` | Additional volumeClaims to add, concatenated with `volumeClaims` above at render time. |
| frontend.extraVolumeMounts | list | `[]` | Additional volumeMounts to add, concatenated with `volumeMounts` above at render time. |
| frontend.extraVolumes | list | `[]` | Additional volumes to add, concatenated with `volumes` above at render time (e.g. to mount a cert or config from a values override without repeating the chart's own volumes). |
| frontend.hostAliases | list | `[]` | Host aliases that will be injected at pod-level into /etc/hosts. |
| frontend.hostNetwork | bool | `false` | Share the host network namespace. Container ports then bind directly on the node, so they must not collide with anything else running there. |
| frontend.hostPID | bool | `false` | Share the host PID namespace (lets the container see and signal host processes). |
| frontend.imagePullSecrets | list | `[]` | Image credentials configuration. |
| frontend.initContainers | list | `[]` | Init containers to add to the app pod. |
| frontend.nodeSelector | object | `{}` | Default node selector for app. |
| frontend.podAnnotations | object | `{}` | Annotations for the app deployed pods. |
| frontend.podLabels | object | `{}` | Labels for the app deployed pods. |
| frontend.podSecurityContext | object | `{"fsGroup":1000,"fsGroupChangePolicy":"OnRootMismatch","runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000,"seccompProfile":{"type":"RuntimeDefault"}}` | Pod-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard. Rendered via `toYaml`, so any `PodSecurityContext` field is accepted. Adjust the UID/GID to whatever your image actually ships with - `runAsNonRoot` makes the kubelet refuse to start a container that would run as root, which is the intended failure mode rather than something to switch off. Set to `null` to omit the block entirely. |
| frontend.priorityClassName | string | `""` | PriorityClass to schedule the pods with (e.g. `system-node-critical` for a node agent that must not be evicted under pressure). |
| frontend.replicaCount | int | `1` | The number of application controller pods to run. Ignored when `deploymentType` is "DaemonSet" (one pod per node) or when `autoscaling.enabled` is true. |
| frontend.revisionHistoryLimit | int | `10` | Revision history limit for the app. |
| frontend.securityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"privileged":false,"readOnlyRootFilesystem":true,"runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000}` | Container-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard: no privilege escalation, no capabilities, immutable root filesystem. Rendered via `toYaml`, so any `SecurityContext` field is accepted. Note `readOnlyRootFilesystem` requires the app to write only to mounted volumes - the default `volumes`/`volumeMounts` below provide an `emptyDir` on /tmp for that reason. Set to `null` to omit the block entirely. |
| frontend.terminationGracePeriodSeconds | int | `null` (Kubernetes default of 30) | Grace period, in seconds, given to the pod to shut down cleanly before it is killed. |
| frontend.tolerations | list | `[]` | Default tolerations for app. |
| frontend.topologySpreadConstraints | list | `[]` | Topology spread constraints used to spread the pods across failure domains. |
| frontend.updateStrategy | object | `{}` | Update strategy applied when `deploymentType` is "StatefulSet" or "DaemonSet" (ignored for a Deployment, which uses `strategy` above). Rendered verbatim via `toYaml`, so it takes the native `StatefulSetUpdateStrategy`/`DaemonSetUpdateStrategy` shape of the selected kind; left empty, Kubernetes applies its own default (`RollingUpdate` for both). |
| frontend.volumeClaims | list | `[]` | List of volumeClaims to add, rendered as the StatefulSet's `volumeClaimTemplates`. Requires `deploymentType: "StatefulSet"` - setting it on a Deployment or DaemonSet fails at render time rather than being silently dropped (use `volumes`/`extraVolumes` there instead). |
| frontend.volumeMounts | list | `[{"mountPath":"/tmp","name":"tmp"}]` | List of mounts to add (normally used with `volumes` or `volumeClaims`). Prefer this for mounts the chart itself always needs; use `extraVolumeMounts` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to the `/tmp` mount backing the hardened `readOnlyRootFilesystem` default (see `volumes` above). |
| frontend.volumes | list | `[{"emptyDir":{},"name":"tmp"}]` | List of volumes to add. Prefer this for volumes the chart itself always needs (e.g. security-hardening `emptyDir`s); use `extraVolumes` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to a `/tmp` `emptyDir`, which is what makes the default `securityContext.readOnlyRootFilesystem: true` usable - drop it only if you also relax that. Helm replaces lists wholesale rather than merging them, so overriding this key means restating the entries you want to keep. |

#### Autoscaling

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| frontend.autoscaling.enabled | bool | `false` | Enable Horizontal Pod Autoscaler for the app. |
| frontend.autoscaling.maxReplicas | int | `3` | Maximum number of replicas for the app. |
| frontend.autoscaling.minReplicas | int | `1` | Minimum number of replicas for the app. |
| frontend.autoscaling.targetCPUUtilizationPercentage | int | `80` | Average CPU utilization percentage for the app. |
| frontend.autoscaling.targetMemoryUtilizationPercentage | int | `80` | Average memory utilization percentage for the app. |

#### GrpcRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| frontend.grpcRoute.annotations | object | `{}` | Additional GRPCRoute annotations. |
| frontend.grpcRoute.enabled | bool | `false` | Enable a GRPCRoute resource for this service. |
| frontend.grpcRoute.hostnames | list | `[]` | Hostnames for the GRPCRoute to match. |
| frontend.grpcRoute.labels | object | `{}` | Additional GRPCRoute labels. |
| frontend.grpcRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the GRPCRoute to. |
| frontend.grpcRoute.rules | list | `[]` | Routing rules for the GRPCRoute. |

#### HttpRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| frontend.httpRoute.annotations | object | `{}` | Additional HTTPRoute annotations. |
| frontend.httpRoute.enabled | bool | `false` | Enable an HTTPRoute resource for this service. |
| frontend.httpRoute.hostnames | list | `[]` | Hostnames for the HTTPRoute to match. |
| frontend.httpRoute.labels | object | `{}` | Additional HTTPRoute labels. |
| frontend.httpRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the HTTPRoute to. |
| frontend.httpRoute.rules | list | `[]` | Routing rules for the HTTPRoute. |

#### Image

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| frontend.image.digest | string | `""` | Image digest (`sha256:...`). When set it takes precedence over `tag`, pinning the exact image content so the same release can never resolve to a different build - preferred over a mutable tag for anything you deploy to production. |
| frontend.image.pullPolicy | string | `"IfNotPresent"` | Image pull policy for the app. |
| frontend.image.registry | string | `"ghcr.io"` | Registry to use for the app. |
| frontend.image.repository | string | `"ia-generative/mille-feuille/frontend"` | Repository to use for the app. |
| frontend.image.tag | string | `""` | Tag to use for the app. Overrides the image tag whose default is the chart appVersion. |

#### Ingress

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| frontend.ingress.annotations | object | `{}` | Additional ingress annotations. |
| frontend.ingress.className | string | `""` | Defines which ingress controller will implement the resource. |
| frontend.ingress.enabled | bool | `false` | Whether or not ingress should be enabled. |
| frontend.ingress.hosts[0].name | string | `"domain.local"` | Name of the host record. |
| frontend.ingress.hosts[0].paths | list | `[{"backend":{"portNumber":null,"serviceName":""},"path":"/","pathType":"Prefix"}]` | Paths of the host record to manage routing (avoids repeating the same host for multiple paths/backends). |
| frontend.ingress.hosts[0].paths[0].backend.portNumber | string | `nil` | Port used by the backend service linked to the path (leave null to use the app service port). |
| frontend.ingress.hosts[0].paths[0].backend.serviceName | string | `""` | Name of the backend service linked to the path (leave empty to use the app service). |
| frontend.ingress.hosts[0].paths[0].path | string | `"/"` | Path of the host record to manage routing. |
| frontend.ingress.hosts[0].paths[0].pathType | string | `"Prefix"` | Path type of the host record. |
| frontend.ingress.labels | object | `{}` | Additional ingress labels. |
| frontend.ingress.tls | list | `[]` | Enable TLS configuration. |

#### Metrics

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| frontend.metrics.enabled | bool | `false` | Deploy metrics service. |
| frontend.metrics.service.annotations | object | `{}` | Metrics service annotations. |
| frontend.metrics.service.labels | object | `{}` | Metrics service labels. |
| frontend.metrics.service.port | int | `9000` | Metrics service port. |
| frontend.metrics.service.portName | string | `"metrics"` | Metrics service port name. |
| frontend.metrics.service.targetPort | int | `9000` | Metrics service target port. |
| frontend.metrics.service.type | string | `"ClusterIP"` | Type of metrics service to create. |
| frontend.metrics.serviceMonitor.annotations | object | `{}` | Prometheus ServiceMonitor annotations. |
| frontend.metrics.serviceMonitor.enabled | bool | `false` | Enable a prometheus ServiceMonitor. |
| frontend.metrics.serviceMonitor.endpoints[0].basicAuth.password | string | `""` | The secret in the service monitor namespace that contains the password for authentication. |
| frontend.metrics.serviceMonitor.endpoints[0].basicAuth.username | string | `""` | The secret in the service monitor namespace that contains the username for authentication. |
| frontend.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.key | string | `""` | Secret key to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| frontend.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.name | string | `""` | Secret name to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| frontend.metrics.serviceMonitor.endpoints[0].honorLabels | bool | `false` | When true, honorLabels preserves the metric’s labels when they collide with the target’s labels. |
| frontend.metrics.serviceMonitor.endpoints[0].interval | string | `"30s"` | Prometheus ServiceMonitor interval. |
| frontend.metrics.serviceMonitor.endpoints[0].metricRelabelings | list | `[]` | Prometheus MetricRelabelConfigs to apply to samples before ingestion. |
| frontend.metrics.serviceMonitor.endpoints[0].path | string | `"/metrics"` | Path used by the Prometheus ServiceMonitor to scrape metrics. |
| frontend.metrics.serviceMonitor.endpoints[0].relabelings | list | `[]` | Prometheus RelabelConfigs to apply to samples before scraping. |
| frontend.metrics.serviceMonitor.endpoints[0].scheme | string | `""` | Prometheus ServiceMonitor scheme. |
| frontend.metrics.serviceMonitor.endpoints[0].scrapeTimeout | string | `"10s"` | Prometheus ServiceMonitor scrapeTimeout. If empty, Prometheus uses the global scrape timeout unless it is less than the target's scrape interval value in which the latter is used. |
| frontend.metrics.serviceMonitor.endpoints[0].selector | object | `{}` | Prometheus ServiceMonitor selector. |
| frontend.metrics.serviceMonitor.endpoints[0].tlsConfig | object | `{}` | Prometheus ServiceMonitor tlsConfig. |
| frontend.metrics.serviceMonitor.labels | object | `{}` | Prometheus ServiceMonitor labels. |

#### NetworkPolicy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| frontend.networkPolicy.annotations | object | `{}` | Annotations to be added to the app NetworkPolicy. |
| frontend.networkPolicy.create | bool | `false` | Create NetworkPolicy object for the app. The policy always selects this component's pods only (via its selector labels), never the whole namespace. |
| frontend.networkPolicy.egress | list | `[]` | Egress rules for the NetworkPolicy object. |
| frontend.networkPolicy.ingress | list | `[]` | Ingress rules for the NetworkPolicy object. |
| frontend.networkPolicy.labels | object | `{}` | Labels to be added to the app NetworkPolicy. |
| frontend.networkPolicy.policyTypes | list | `["Ingress"]` | Policy types used in the NetworkPolicy object. |

#### Pdb

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| frontend.pdb.annotations | object | `{}` | Annotations to be added to app pdb. |
| frontend.pdb.enabled | bool | `false` | Deploy a PodDisruptionBudget for the app |
| frontend.pdb.labels | object | `{}` | Labels to be added to app pdb. |
| frontend.pdb.maxUnavailable | string | `""` | Number of pods that are unavailable after eviction as number or percentage (eg.: 50%). Has higher precedence over `frontend.pdb.minAvailable`. |
| frontend.pdb.minAvailable | string | `""` | Number of pods that are available after eviction as number or percentage (eg.: 50%). One of `minAvailable` / `maxUnavailable` must be set when `pdb.enabled` is true - a budget of 0 is the same as having no budget at all, so leaving both empty fails at render time. |

#### Probes

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| frontend.probes.livenessProbe.failureThreshold | int | `3` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| frontend.probes.livenessProbe.httpGet.path | string | `"/"` | Frontend container healthcheck endpoint (livenessProbe is defined using `toYaml` so it is possible to override it completely). |
| frontend.probes.livenessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| frontend.probes.livenessProbe.initialDelaySeconds | int | `30` | Number of seconds after the container has started before probe is initiated. |
| frontend.probes.livenessProbe.periodSeconds | int | `30` | How often (in seconds) to perform the probe. |
| frontend.probes.livenessProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| frontend.probes.livenessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| frontend.probes.readinessProbe.failureThreshold | int | `2` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| frontend.probes.readinessProbe.httpGet.path | string | `"/"` | Frontend container healthcheck endpoint (readinessProbe is defined using `toYaml` so it is possible to override it completely). |
| frontend.probes.readinessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| frontend.probes.readinessProbe.initialDelaySeconds | int | `10` | Number of seconds after the container has started before probe is initiated. |
| frontend.probes.readinessProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| frontend.probes.readinessProbe.successThreshold | int | `2` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| frontend.probes.readinessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| frontend.probes.startupProbe.failureThreshold | int | `10` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| frontend.probes.startupProbe.httpGet.path | string | `"/"` | Frontend container healthcheck endpoint (startupProbe is defined using `toYaml` so it is possible to override it completely). |
| frontend.probes.startupProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| frontend.probes.startupProbe.initialDelaySeconds | int | `0` | Number of seconds after the container has started before probe is initiated. |
| frontend.probes.startupProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| frontend.probes.startupProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| frontend.probes.startupProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |

#### Resources

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| frontend.resources.limits.cpu | string | `"500m"` | CPU limit for the app. |
| frontend.resources.limits.memory | string | `"2Gi"` | Memory limit for the app. |
| frontend.resources.requests.cpu | string | `"100m"` | CPU request for the app. |
| frontend.resources.requests.memory | string | `"256Mi"` | Memory request for the app. |

#### Service

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| frontend.service.enabled | bool | `true` | Whether or not to create a Service for the app. Set to `false` for components that don't accept traffic (e.g. a queue consumer with no `containerPort`). |
| frontend.service.extraPorts | list | `[]` | Extra service ports. |
| frontend.service.nodePort | int | `null` (allocated by Kubernetes) | Port used when type is `NodePort` to expose the service on the given node port. Left empty, Kubernetes allocates one from the configured node-port range, which avoids two releases of this chart colliding on the same hardcoded port. |
| frontend.service.port | int | `80` | Port used by the service. |
| frontend.service.portName | string | `"http"` | Port name used by the service. |
| frontend.service.protocol | string | `"TCP"` | Protocol used by the service. |
| frontend.service.type | string | `"ClusterIP"` | Type of service to create for the app. |

#### ServiceAccount

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| frontend.serviceAccount.annotations | object | `{}` | Annotations applied to created service account. |
| frontend.serviceAccount.automountServiceAccountToken | bool | `false` | Should the service account access token be automount in the pod. |
| frontend.serviceAccount.clusterRole.create | bool | `false` | Should the clusterRole be created. |
| frontend.serviceAccount.clusterRole.rules | list | `[]` | ClusterRole rules associated with the service account. |
| frontend.serviceAccount.create | bool | `false` | Create a service account. |
| frontend.serviceAccount.enabled | bool | `false` | Enable the service account. |
| frontend.serviceAccount.name | string | `""` | Service account name. |
| frontend.serviceAccount.role.create | bool | `false` | Should the role be created. |
| frontend.serviceAccount.role.rules | list | `[]` | Role rules associated with the service account. |

#### Strategy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| frontend.strategy.rollingUpdate.maxSurge | int | `1` | The maximum number of pods that can be scheduled above the desired number of pods. |
| frontend.strategy.rollingUpdate.maxUnavailable | int | `1` | The maximum number of pods that can be unavailable during the update process. |
| frontend.strategy.type | string | `"RollingUpdate"` | Strategy type used to replace old Pods by new ones, can be `Recreate` or `RollingUpdate`. Only applied when `deploymentType` is "Deployment". |

### Gateway

#### General

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| gateway.addresses | list | `[]` | Gateway addresses configuration. |
| gateway.annotations | object | `{}` | Additional gateway annotations. |
| gateway.className | string | `""` | GatewayClass name. Required when creating a Gateway. |
| gateway.create | bool | `false` | Create a Gateway resource. Usually, you reference an existing Gateway managed by the infrastructure team. |
| gateway.labels | object | `{}` | Additional gateway labels. |
| gateway.listeners | list | `[]` | Gateway listeners configuration. |
| gateway.name | string | `""` | Name of the Gateway resource. If not set, uses the release fullname. |

### Jobs

#### Migration

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| jobs.migration.hook | object | `{"deletePolicy":"before-hook-creation,hook-succeeded","enabled":true,"types":["pre-install","pre-upgrade"],"weight":0}` | Run as a Helm hook so migrations execute before the new version serves traffic (pre-install + pre-upgrade). |

### Redis

#### General

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| redis.architecture | string | `"standalone"` |  |
| redis.enabled | bool | `true` |  |
| redis.fullnameOverride | string | `"millefeuille-redis"` |  |

#### Auth

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| redis.auth.enabled | bool | `false` |  |

#### Resources

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| redis.resources.limits.cpu | string | `"250m"` |  |
| redis.resources.limits.memory | string | `"256Mi"` |  |
| redis.resources.requests.cpu | string | `"100m"` |  |
| redis.resources.requests.memory | string | `"128Mi"` |  |

### WorkerAgent

#### General

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_agent.affinity | object | `{}` | Affinity used for app pod. |
| worker_agent.args | list | `[]` | Worker_agent container command args. |
| worker_agent.automountServiceAccountToken | bool | `false` | Mount the ServiceAccount token into the app pods. Defaults to false so a compromised container holds no API credentials; the API server does not need the token unless the app actually talks to the Kubernetes API. Applied at pod level so it holds even when `serviceAccount.name` points at an SA that automounts. |
| worker_agent.command | list | `[]` | Worker_agent container command. |
| worker_agent.containerPort | int | `8080` | Worker_agent container port number. Set to `null`/`0` (and disable `service`/probes) for components that don't listen on any port (e.g. a queue consumer). |
| worker_agent.containerPortName | string | `"http"` | Worker_agent container port name. |
| worker_agent.deploymentType | string | `"Deployment"` | Workload kind to deploy the app as. One of "Deployment", "StatefulSet" or "DaemonSet" (validated at render time - an unknown value fails instead of producing a release with no workload). Use the top-level `jobs` / `cronjobs` maps for one-off or scheduled workloads. Some values only apply to certain kinds: `replicaCount`/`autoscaling` and `strategy` are Deployment-only (`autoscaling` also works on a StatefulSet), `volumeClaims`/`extraVolumeClaims` are StatefulSet-only, and `updateStrategy` covers StatefulSet and DaemonSet. |
| worker_agent.dnsConfig | object | `{}` | Pod DNS configuration, merged with `dnsPolicy` by the kubelet. |
| worker_agent.dnsPolicy | string | `""` (`ClusterFirstWithHostNet` when `hostNetwork` is true) | Pod DNS policy. Left empty, it defaults to `ClusterFirstWithHostNet` when `hostNetwork` is true (otherwise a hostNetwork pod silently stops resolving cluster DNS) and to the Kubernetes default `ClusterFirst` when it isn't. |
| worker_agent.enableServiceLinks | bool | `false` | Inject the legacy `{SVC}_SERVICE_HOST`/`_PORT` environment variables for every Service in the namespace. Defaults to false: the variables are rarely used, leak the namespace's topology into every container, and can collide with the app's own configuration. Set to true only for an app that genuinely reads them. |
| worker_agent.env | object | `{}` | Map or array of environment variables to inject into the app container (`valueFrom` supported). |
| worker_agent.envCm | object | `{}` | Map of environment variables to inject into a configmap loaded by the app container (`valueFrom` not supported). |
| worker_agent.envFrom | list | `[]` | Worker_agent container env variables loaded from configmap or secret reference. List or map (merged with `global.envFrom` above, global entries first); see `global.envFrom` for both forms. |
| worker_agent.envSecret | object | `{}` | Map of environment variables to inject into a secret loaded by the app container (`valueFrom` not supported). Values placed here are stored in plain text in the values file AND in the Helm release secret, so use it for non-sensitive-but-secret-shaped config only. For real credentials prefer referencing a Secret you manage elsewhere via `envFrom`, or have an operator materialise it (see the `VaultStaticSecret` example under `extraObjects`). |
| worker_agent.extraContainers | list | `[]` | Extra containers to add to the app pod as sidecars. |
| worker_agent.extraPorts | list | `[]` | Worker_agent extra container ports. |
| worker_agent.extraVolumeClaims | list | `[]` | Additional volumeClaims to add, concatenated with `volumeClaims` above at render time. |
| worker_agent.extraVolumeMounts | list | `[]` | Additional volumeMounts to add, concatenated with `volumeMounts` above at render time. |
| worker_agent.extraVolumes | list | `[]` | Additional volumes to add, concatenated with `volumes` above at render time (e.g. to mount a cert or config from a values override without repeating the chart's own volumes). |
| worker_agent.hostAliases | list | `[]` | Host aliases that will be injected at pod-level into /etc/hosts. |
| worker_agent.hostNetwork | bool | `false` | Share the host network namespace. Container ports then bind directly on the node, so they must not collide with anything else running there. |
| worker_agent.hostPID | bool | `false` | Share the host PID namespace (lets the container see and signal host processes). |
| worker_agent.imagePullSecrets | list | `[]` | Image credentials configuration. |
| worker_agent.initContainers | list | `[]` | Init containers to add to the app pod. |
| worker_agent.nodeSelector | object | `{}` | Default node selector for app. |
| worker_agent.podAnnotations | object | `{}` | Annotations for the app deployed pods. |
| worker_agent.podLabels | object | `{}` | Labels for the app deployed pods. |
| worker_agent.podSecurityContext | object | `{"fsGroup":1000,"fsGroupChangePolicy":"OnRootMismatch","runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000,"seccompProfile":{"type":"RuntimeDefault"}}` | Pod-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard. Rendered via `toYaml`, so any `PodSecurityContext` field is accepted. Adjust the UID/GID to whatever your image actually ships with - `runAsNonRoot` makes the kubelet refuse to start a container that would run as root, which is the intended failure mode rather than something to switch off. Set to `null` to omit the block entirely. |
| worker_agent.priorityClassName | string | `""` | PriorityClass to schedule the pods with (e.g. `system-node-critical` for a node agent that must not be evicted under pressure). |
| worker_agent.replicaCount | int | `1` | The number of application controller pods to run. Ignored when `deploymentType` is "DaemonSet" (one pod per node) or when `autoscaling.enabled` is true. |
| worker_agent.revisionHistoryLimit | int | `10` | Revision history limit for the app. |
| worker_agent.securityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"privileged":false,"readOnlyRootFilesystem":true,"runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000}` | Container-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard: no privilege escalation, no capabilities, immutable root filesystem. Rendered via `toYaml`, so any `SecurityContext` field is accepted. Note `readOnlyRootFilesystem` requires the app to write only to mounted volumes - the default `volumes`/`volumeMounts` below provide an `emptyDir` on /tmp for that reason. Set to `null` to omit the block entirely. |
| worker_agent.terminationGracePeriodSeconds | int | `null` (Kubernetes default of 30) | Grace period, in seconds, given to the pod to shut down cleanly before it is killed. |
| worker_agent.tolerations | list | `[]` | Default tolerations for app. |
| worker_agent.topologySpreadConstraints | list | `[]` | Topology spread constraints used to spread the pods across failure domains. |
| worker_agent.updateStrategy | object | `{}` | Update strategy applied when `deploymentType` is "StatefulSet" or "DaemonSet" (ignored for a Deployment, which uses `strategy` above). Rendered verbatim via `toYaml`, so it takes the native `StatefulSetUpdateStrategy`/`DaemonSetUpdateStrategy` shape of the selected kind; left empty, Kubernetes applies its own default (`RollingUpdate` for both). |
| worker_agent.volumeClaims | list | `[]` | List of volumeClaims to add, rendered as the StatefulSet's `volumeClaimTemplates`. Requires `deploymentType: "StatefulSet"` - setting it on a Deployment or DaemonSet fails at render time rather than being silently dropped (use `volumes`/`extraVolumes` there instead). |
| worker_agent.volumeMounts | list | `[{"mountPath":"/tmp","name":"tmp"}]` | List of mounts to add (normally used with `volumes` or `volumeClaims`). Prefer this for mounts the chart itself always needs; use `extraVolumeMounts` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to the `/tmp` mount backing the hardened `readOnlyRootFilesystem` default (see `volumes` above). |
| worker_agent.volumes | list | `[{"emptyDir":{},"name":"tmp"}]` | List of volumes to add. Prefer this for volumes the chart itself always needs (e.g. security-hardening `emptyDir`s); use `extraVolumes` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to a `/tmp` `emptyDir`, which is what makes the default `securityContext.readOnlyRootFilesystem: true` usable - drop it only if you also relax that. Helm replaces lists wholesale rather than merging them, so overriding this key means restating the entries you want to keep. |

#### Autoscaling

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_agent.autoscaling.enabled | bool | `false` | Enable Horizontal Pod Autoscaler for the app. |
| worker_agent.autoscaling.maxReplicas | int | `3` | Maximum number of replicas for the app. |
| worker_agent.autoscaling.minReplicas | int | `1` | Minimum number of replicas for the app. |
| worker_agent.autoscaling.targetCPUUtilizationPercentage | int | `80` | Average CPU utilization percentage for the app. |
| worker_agent.autoscaling.targetMemoryUtilizationPercentage | int | `80` | Average memory utilization percentage for the app. |

#### GrpcRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_agent.grpcRoute.annotations | object | `{}` | Additional GRPCRoute annotations. |
| worker_agent.grpcRoute.enabled | bool | `false` | Enable a GRPCRoute resource for this service. |
| worker_agent.grpcRoute.hostnames | list | `[]` | Hostnames for the GRPCRoute to match. |
| worker_agent.grpcRoute.labels | object | `{}` | Additional GRPCRoute labels. |
| worker_agent.grpcRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the GRPCRoute to. |
| worker_agent.grpcRoute.rules | list | `[]` | Routing rules for the GRPCRoute. |

#### HttpRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_agent.httpRoute.annotations | object | `{}` | Additional HTTPRoute annotations. |
| worker_agent.httpRoute.enabled | bool | `false` | Enable an HTTPRoute resource for this service. |
| worker_agent.httpRoute.hostnames | list | `[]` | Hostnames for the HTTPRoute to match. |
| worker_agent.httpRoute.labels | object | `{}` | Additional HTTPRoute labels. |
| worker_agent.httpRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the HTTPRoute to. |
| worker_agent.httpRoute.rules | list | `[]` | Routing rules for the HTTPRoute. |

#### Image

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_agent.image.digest | string | `""` | Image digest (`sha256:...`). When set it takes precedence over `tag`, pinning the exact image content so the same release can never resolve to a different build - preferred over a mutable tag for anything you deploy to production. |
| worker_agent.image.pullPolicy | string | `"IfNotPresent"` | Image pull policy for the app. |
| worker_agent.image.registry | string | `"ghcr.io"` | Registry to use for the app. |
| worker_agent.image.repository | string | `"ia-generative/mille-feuille/worker-agent-execution"` | Repository to use for the app. |
| worker_agent.image.tag | string | `""` | Tag to use for the app. Overrides the image tag whose default is the chart appVersion. |

#### Ingress

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_agent.ingress.annotations | object | `{}` | Additional ingress annotations. |
| worker_agent.ingress.className | string | `""` | Defines which ingress controller will implement the resource. |
| worker_agent.ingress.enabled | bool | `false` | Whether or not ingress should be enabled. |
| worker_agent.ingress.hosts[0].name | string | `"domain.local"` | Name of the host record. |
| worker_agent.ingress.hosts[0].paths | list | `[{"backend":{"portNumber":null,"serviceName":""},"path":"/","pathType":"Prefix"}]` | Paths of the host record to manage routing (avoids repeating the same host for multiple paths/backends). |
| worker_agent.ingress.hosts[0].paths[0].backend.portNumber | string | `nil` | Port used by the backend service linked to the path (leave null to use the app service port). |
| worker_agent.ingress.hosts[0].paths[0].backend.serviceName | string | `""` | Name of the backend service linked to the path (leave empty to use the app service). |
| worker_agent.ingress.hosts[0].paths[0].path | string | `"/"` | Path of the host record to manage routing. |
| worker_agent.ingress.hosts[0].paths[0].pathType | string | `"Prefix"` | Path type of the host record. |
| worker_agent.ingress.labels | object | `{}` | Additional ingress labels. |
| worker_agent.ingress.tls | list | `[]` | Enable TLS configuration. |

#### Metrics

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_agent.metrics.enabled | bool | `false` | Deploy metrics service. |
| worker_agent.metrics.service.annotations | object | `{}` | Metrics service annotations. |
| worker_agent.metrics.service.labels | object | `{}` | Metrics service labels. |
| worker_agent.metrics.service.port | int | `9000` | Metrics service port. |
| worker_agent.metrics.service.portName | string | `"metrics"` | Metrics service port name. |
| worker_agent.metrics.service.targetPort | int | `9000` | Metrics service target port. |
| worker_agent.metrics.service.type | string | `"ClusterIP"` | Type of metrics service to create. |
| worker_agent.metrics.serviceMonitor.annotations | object | `{}` | Prometheus ServiceMonitor annotations. |
| worker_agent.metrics.serviceMonitor.enabled | bool | `false` | Enable a prometheus ServiceMonitor. |
| worker_agent.metrics.serviceMonitor.endpoints[0].basicAuth.password | string | `""` | The secret in the service monitor namespace that contains the password for authentication. |
| worker_agent.metrics.serviceMonitor.endpoints[0].basicAuth.username | string | `""` | The secret in the service monitor namespace that contains the username for authentication. |
| worker_agent.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.key | string | `""` | Secret key to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| worker_agent.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.name | string | `""` | Secret name to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| worker_agent.metrics.serviceMonitor.endpoints[0].honorLabels | bool | `false` | When true, honorLabels preserves the metric’s labels when they collide with the target’s labels. |
| worker_agent.metrics.serviceMonitor.endpoints[0].interval | string | `"30s"` | Prometheus ServiceMonitor interval. |
| worker_agent.metrics.serviceMonitor.endpoints[0].metricRelabelings | list | `[]` | Prometheus MetricRelabelConfigs to apply to samples before ingestion. |
| worker_agent.metrics.serviceMonitor.endpoints[0].path | string | `"/metrics"` | Path used by the Prometheus ServiceMonitor to scrape metrics. |
| worker_agent.metrics.serviceMonitor.endpoints[0].relabelings | list | `[]` | Prometheus RelabelConfigs to apply to samples before scraping. |
| worker_agent.metrics.serviceMonitor.endpoints[0].scheme | string | `""` | Prometheus ServiceMonitor scheme. |
| worker_agent.metrics.serviceMonitor.endpoints[0].scrapeTimeout | string | `"10s"` | Prometheus ServiceMonitor scrapeTimeout. If empty, Prometheus uses the global scrape timeout unless it is less than the target's scrape interval value in which the latter is used. |
| worker_agent.metrics.serviceMonitor.endpoints[0].selector | object | `{}` | Prometheus ServiceMonitor selector. |
| worker_agent.metrics.serviceMonitor.endpoints[0].tlsConfig | object | `{}` | Prometheus ServiceMonitor tlsConfig. |
| worker_agent.metrics.serviceMonitor.labels | object | `{}` | Prometheus ServiceMonitor labels. |

#### NetworkPolicy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_agent.networkPolicy.annotations | object | `{}` | Annotations to be added to the app NetworkPolicy. |
| worker_agent.networkPolicy.create | bool | `false` | Create NetworkPolicy object for the app. The policy always selects this component's pods only (via its selector labels), never the whole namespace. |
| worker_agent.networkPolicy.egress | list | `[]` | Egress rules for the NetworkPolicy object. |
| worker_agent.networkPolicy.ingress | list | `[]` | Ingress rules for the NetworkPolicy object. |
| worker_agent.networkPolicy.labels | object | `{}` | Labels to be added to the app NetworkPolicy. |
| worker_agent.networkPolicy.policyTypes | list | `["Ingress"]` | Policy types used in the NetworkPolicy object. |

#### Pdb

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_agent.pdb.annotations | object | `{}` | Annotations to be added to app pdb. |
| worker_agent.pdb.enabled | bool | `false` | Deploy a PodDisruptionBudget for the app |
| worker_agent.pdb.labels | object | `{}` | Labels to be added to app pdb. |
| worker_agent.pdb.maxUnavailable | string | `""` | Number of pods that are unavailable after eviction as number or percentage (eg.: 50%). Has higher precedence over `worker_agent.pdb.minAvailable`. |
| worker_agent.pdb.minAvailable | string | `""` | Number of pods that are available after eviction as number or percentage (eg.: 50%). One of `minAvailable` / `maxUnavailable` must be set when `pdb.enabled` is true - a budget of 0 is the same as having no budget at all, so leaving both empty fails at render time. |

#### Probes

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_agent.probes.livenessProbe.failureThreshold | int | `3` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_agent.probes.livenessProbe.httpGet.path | string | `"/"` | Worker_agent container healthcheck endpoint (livenessProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_agent.probes.livenessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_agent.probes.livenessProbe.initialDelaySeconds | int | `30` | Number of seconds after the container has started before probe is initiated. |
| worker_agent.probes.livenessProbe.periodSeconds | int | `30` | How often (in seconds) to perform the probe. |
| worker_agent.probes.livenessProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_agent.probes.livenessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| worker_agent.probes.readinessProbe.failureThreshold | int | `2` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_agent.probes.readinessProbe.httpGet.path | string | `"/"` | Worker_agent container healthcheck endpoint (readinessProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_agent.probes.readinessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_agent.probes.readinessProbe.initialDelaySeconds | int | `10` | Number of seconds after the container has started before probe is initiated. |
| worker_agent.probes.readinessProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| worker_agent.probes.readinessProbe.successThreshold | int | `2` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_agent.probes.readinessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| worker_agent.probes.startupProbe.failureThreshold | int | `10` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_agent.probes.startupProbe.httpGet.path | string | `"/"` | Worker_agent container healthcheck endpoint (startupProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_agent.probes.startupProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_agent.probes.startupProbe.initialDelaySeconds | int | `0` | Number of seconds after the container has started before probe is initiated. |
| worker_agent.probes.startupProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| worker_agent.probes.startupProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_agent.probes.startupProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |

#### Resources

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_agent.resources.limits.cpu | string | `"500m"` | CPU limit for the app. |
| worker_agent.resources.limits.memory | string | `"2Gi"` | Memory limit for the app. |
| worker_agent.resources.requests.cpu | string | `"100m"` | CPU request for the app. |
| worker_agent.resources.requests.memory | string | `"256Mi"` | Memory request for the app. |

#### Service

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_agent.service.enabled | bool | `true` | Whether or not to create a Service for the app. Set to `false` for components that don't accept traffic (e.g. a queue consumer with no `containerPort`). |
| worker_agent.service.extraPorts | list | `[]` | Extra service ports. |
| worker_agent.service.nodePort | int | `null` (allocated by Kubernetes) | Port used when type is `NodePort` to expose the service on the given node port. Left empty, Kubernetes allocates one from the configured node-port range, which avoids two releases of this chart colliding on the same hardcoded port. |
| worker_agent.service.port | int | `80` | Port used by the service. |
| worker_agent.service.portName | string | `"http"` | Port name used by the service. |
| worker_agent.service.protocol | string | `"TCP"` | Protocol used by the service. |
| worker_agent.service.type | string | `"ClusterIP"` | Type of service to create for the app. |

#### ServiceAccount

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_agent.serviceAccount.annotations | object | `{}` | Annotations applied to created service account. |
| worker_agent.serviceAccount.automountServiceAccountToken | bool | `false` | Should the service account access token be automount in the pod. |
| worker_agent.serviceAccount.clusterRole.create | bool | `false` | Should the clusterRole be created. |
| worker_agent.serviceAccount.clusterRole.rules | list | `[]` | ClusterRole rules associated with the service account. |
| worker_agent.serviceAccount.create | bool | `false` | Create a service account. |
| worker_agent.serviceAccount.enabled | bool | `false` | Enable the service account. |
| worker_agent.serviceAccount.name | string | `""` | Service account name. |
| worker_agent.serviceAccount.role.create | bool | `false` | Should the role be created. |
| worker_agent.serviceAccount.role.rules | list | `[]` | Role rules associated with the service account. |

#### Strategy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_agent.strategy.rollingUpdate.maxSurge | int | `1` | The maximum number of pods that can be scheduled above the desired number of pods. |
| worker_agent.strategy.rollingUpdate.maxUnavailable | int | `1` | The maximum number of pods that can be unavailable during the update process. |
| worker_agent.strategy.type | string | `"RollingUpdate"` | Strategy type used to replace old Pods by new ones, can be `Recreate` or `RollingUpdate`. Only applied when `deploymentType` is "Deployment". |

### WorkerAsyncApi

#### General

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_async_api.affinity | object | `{}` | Affinity used for app pod. |
| worker_async_api.args | list | `[]` | Worker_async_api container command args. |
| worker_async_api.automountServiceAccountToken | bool | `false` | Mount the ServiceAccount token into the app pods. Defaults to false so a compromised container holds no API credentials; the API server does not need the token unless the app actually talks to the Kubernetes API. Applied at pod level so it holds even when `serviceAccount.name` points at an SA that automounts. |
| worker_async_api.command | list | `[]` | Worker_async_api container command. |
| worker_async_api.containerPort | int | `8084` | Worker_async_api container port number. Set to `null`/`0` (and disable `service`/probes) for components that don't listen on any port (e.g. a queue consumer). |
| worker_async_api.containerPortName | string | `"http"` | Worker_async_api container port name. |
| worker_async_api.deploymentType | string | `"Deployment"` | Workload kind to deploy the app as. One of "Deployment", "StatefulSet" or "DaemonSet" (validated at render time - an unknown value fails instead of producing a release with no workload). Use the top-level `jobs` / `cronjobs` maps for one-off or scheduled workloads. Some values only apply to certain kinds: `replicaCount`/`autoscaling` and `strategy` are Deployment-only (`autoscaling` also works on a StatefulSet), `volumeClaims`/`extraVolumeClaims` are StatefulSet-only, and `updateStrategy` covers StatefulSet and DaemonSet. |
| worker_async_api.dnsConfig | object | `{}` | Pod DNS configuration, merged with `dnsPolicy` by the kubelet. |
| worker_async_api.dnsPolicy | string | `""` (`ClusterFirstWithHostNet` when `hostNetwork` is true) | Pod DNS policy. Left empty, it defaults to `ClusterFirstWithHostNet` when `hostNetwork` is true (otherwise a hostNetwork pod silently stops resolving cluster DNS) and to the Kubernetes default `ClusterFirst` when it isn't. |
| worker_async_api.enableServiceLinks | bool | `false` | Inject the legacy `{SVC}_SERVICE_HOST`/`_PORT` environment variables for every Service in the namespace. Defaults to false: the variables are rarely used, leak the namespace's topology into every container, and can collide with the app's own configuration. Set to true only for an app that genuinely reads them. |
| worker_async_api.enabled | bool | `false` | Deploy the AsyncTaskAPI worker (worker/async_api: RabbitMQ consumer, no Celery). Disabled by default: it needs a RabbitMQ broker and the async-api object storage, neither of which this chart provides. See worker/async_api/README.md for the environment variables to set (`env`/`envFrom`). |
| worker_async_api.env | object | `{}` | Map or array of environment variables to inject into the app container (`valueFrom` supported). |
| worker_async_api.envCm | object | `{}` | Map of environment variables to inject into a configmap loaded by the app container (`valueFrom` not supported). |
| worker_async_api.envFrom | list | `[]` | Worker_async_api container env variables loaded from configmap or secret reference. List or map (merged with `global.envFrom` above, global entries first); see `global.envFrom` for both forms. |
| worker_async_api.envSecret | object | `{}` | Map of environment variables to inject into a secret loaded by the app container (`valueFrom` not supported). Values placed here are stored in plain text in the values file AND in the Helm release secret, so use it for non-sensitive-but-secret-shaped config only. For real credentials prefer referencing a Secret you manage elsewhere via `envFrom`, or have an operator materialise it (see the `VaultStaticSecret` example under `extraObjects`). |
| worker_async_api.extraContainers | list | `[]` | Extra containers to add to the app pod as sidecars. |
| worker_async_api.extraPorts | list | `[]` | Worker_async_api extra container ports. |
| worker_async_api.extraVolumeClaims | list | `[]` | Additional volumeClaims to add, concatenated with `volumeClaims` above at render time. |
| worker_async_api.extraVolumeMounts | list | `[]` | Additional volumeMounts to add, concatenated with `volumeMounts` above at render time. |
| worker_async_api.extraVolumes | list | `[]` | Additional volumes to add, concatenated with `volumes` above at render time (e.g. to mount a cert or config from a values override without repeating the chart's own volumes). |
| worker_async_api.hostAliases | list | `[]` | Host aliases that will be injected at pod-level into /etc/hosts. |
| worker_async_api.hostNetwork | bool | `false` | Share the host network namespace. Container ports then bind directly on the node, so they must not collide with anything else running there. |
| worker_async_api.hostPID | bool | `false` | Share the host PID namespace (lets the container see and signal host processes). |
| worker_async_api.imagePullSecrets | list | `[]` | Image credentials configuration. |
| worker_async_api.initContainers | list | `[]` | Init containers to add to the app pod. |
| worker_async_api.nodeSelector | object | `{}` | Default node selector for app. |
| worker_async_api.podAnnotations | object | `{}` | Annotations for the app deployed pods. |
| worker_async_api.podLabels | object | `{}` | Labels for the app deployed pods. |
| worker_async_api.podSecurityContext | object | `{"fsGroup":1000,"fsGroupChangePolicy":"OnRootMismatch","runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000,"seccompProfile":{"type":"RuntimeDefault"}}` | Pod-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard. Rendered via `toYaml`, so any `PodSecurityContext` field is accepted. Adjust the UID/GID to whatever your image actually ships with - `runAsNonRoot` makes the kubelet refuse to start a container that would run as root, which is the intended failure mode rather than something to switch off. Set to `null` to omit the block entirely. |
| worker_async_api.priorityClassName | string | `""` | PriorityClass to schedule the pods with (e.g. `system-node-critical` for a node agent that must not be evicted under pressure). |
| worker_async_api.replicaCount | int | `1` | The number of application controller pods to run. Ignored when `deploymentType` is "DaemonSet" (one pod per node) or when `autoscaling.enabled` is true. |
| worker_async_api.revisionHistoryLimit | int | `10` | Revision history limit for the app. |
| worker_async_api.securityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"privileged":false,"readOnlyRootFilesystem":true,"runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000}` | Container-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard: no privilege escalation, no capabilities, immutable root filesystem. Rendered via `toYaml`, so any `SecurityContext` field is accepted. Note `readOnlyRootFilesystem` requires the app to write only to mounted volumes - the default `volumes`/`volumeMounts` below provide an `emptyDir` on /tmp for that reason. Set to `null` to omit the block entirely. |
| worker_async_api.terminationGracePeriodSeconds | int | `null` (Kubernetes default of 30) | Grace period, in seconds, given to the pod to shut down cleanly before it is killed. |
| worker_async_api.tolerations | list | `[]` | Default tolerations for app. |
| worker_async_api.topologySpreadConstraints | list | `[]` | Topology spread constraints used to spread the pods across failure domains. |
| worker_async_api.updateStrategy | object | `{}` | Update strategy applied when `deploymentType` is "StatefulSet" or "DaemonSet" (ignored for a Deployment, which uses `strategy` above). Rendered verbatim via `toYaml`, so it takes the native `StatefulSetUpdateStrategy`/`DaemonSetUpdateStrategy` shape of the selected kind; left empty, Kubernetes applies its own default (`RollingUpdate` for both). |
| worker_async_api.volumeClaims | list | `[]` | List of volumeClaims to add, rendered as the StatefulSet's `volumeClaimTemplates`. Requires `deploymentType: "StatefulSet"` - setting it on a Deployment or DaemonSet fails at render time rather than being silently dropped (use `volumes`/`extraVolumes` there instead). |
| worker_async_api.volumeMounts | list | `[{"mountPath":"/tmp","name":"tmp"}]` | List of mounts to add (normally used with `volumes` or `volumeClaims`). Prefer this for mounts the chart itself always needs; use `extraVolumeMounts` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to the `/tmp` mount backing the hardened `readOnlyRootFilesystem` default (see `volumes` above). |
| worker_async_api.volumes | list | `[{"emptyDir":{},"name":"tmp"}]` | List of volumes to add. Prefer this for volumes the chart itself always needs (e.g. security-hardening `emptyDir`s); use `extraVolumes` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to a `/tmp` `emptyDir`, which is what makes the default `securityContext.readOnlyRootFilesystem: true` usable - drop it only if you also relax that. Helm replaces lists wholesale rather than merging them, so overriding this key means restating the entries you want to keep. |

#### Autoscaling

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_async_api.autoscaling.enabled | bool | `false` | Enable Horizontal Pod Autoscaler for the app. |
| worker_async_api.autoscaling.maxReplicas | int | `3` | Maximum number of replicas for the app. |
| worker_async_api.autoscaling.minReplicas | int | `1` | Minimum number of replicas for the app. |
| worker_async_api.autoscaling.targetCPUUtilizationPercentage | int | `80` | Average CPU utilization percentage for the app. |
| worker_async_api.autoscaling.targetMemoryUtilizationPercentage | int | `80` | Average memory utilization percentage for the app. |

#### GrpcRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_async_api.grpcRoute.annotations | object | `{}` | Additional GRPCRoute annotations. |
| worker_async_api.grpcRoute.enabled | bool | `false` | Enable a GRPCRoute resource for this service. |
| worker_async_api.grpcRoute.hostnames | list | `[]` | Hostnames for the GRPCRoute to match. |
| worker_async_api.grpcRoute.labels | object | `{}` | Additional GRPCRoute labels. |
| worker_async_api.grpcRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the GRPCRoute to. |
| worker_async_api.grpcRoute.rules | list | `[]` | Routing rules for the GRPCRoute. |

#### HttpRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_async_api.httpRoute.annotations | object | `{}` | Additional HTTPRoute annotations. |
| worker_async_api.httpRoute.enabled | bool | `false` | Enable an HTTPRoute resource for this service. |
| worker_async_api.httpRoute.hostnames | list | `[]` | Hostnames for the HTTPRoute to match. |
| worker_async_api.httpRoute.labels | object | `{}` | Additional HTTPRoute labels. |
| worker_async_api.httpRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the HTTPRoute to. |
| worker_async_api.httpRoute.rules | list | `[]` | Routing rules for the HTTPRoute. |

#### Image

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_async_api.image.digest | string | `""` | Image digest (`sha256:...`). When set it takes precedence over `tag`, pinning the exact image content so the same release can never resolve to a different build - preferred over a mutable tag for anything you deploy to production. |
| worker_async_api.image.pullPolicy | string | `"IfNotPresent"` | Image pull policy for the app. |
| worker_async_api.image.registry | string | `"ghcr.io"` | Registry to use for the app. |
| worker_async_api.image.repository | string | `"ia-generative/mille-feuille/worker-async-api"` | Repository to use for the app. |
| worker_async_api.image.tag | string | `""` | Tag to use for the app. Overrides the image tag whose default is the chart appVersion. |

#### Ingress

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_async_api.ingress.annotations | object | `{}` | Additional ingress annotations. |
| worker_async_api.ingress.className | string | `""` | Defines which ingress controller will implement the resource. |
| worker_async_api.ingress.enabled | bool | `false` | Whether or not ingress should be enabled. |
| worker_async_api.ingress.hosts[0].name | string | `"domain.local"` | Name of the host record. |
| worker_async_api.ingress.hosts[0].paths | list | `[{"backend":{"portNumber":null,"serviceName":""},"path":"/","pathType":"Prefix"}]` | Paths of the host record to manage routing (avoids repeating the same host for multiple paths/backends). |
| worker_async_api.ingress.hosts[0].paths[0].backend.portNumber | string | `nil` | Port used by the backend service linked to the path (leave null to use the app service port). |
| worker_async_api.ingress.hosts[0].paths[0].backend.serviceName | string | `""` | Name of the backend service linked to the path (leave empty to use the app service). |
| worker_async_api.ingress.hosts[0].paths[0].path | string | `"/"` | Path of the host record to manage routing. |
| worker_async_api.ingress.hosts[0].paths[0].pathType | string | `"Prefix"` | Path type of the host record. |
| worker_async_api.ingress.labels | object | `{}` | Additional ingress labels. |
| worker_async_api.ingress.tls | list | `[]` | Enable TLS configuration. |

#### Metrics

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_async_api.metrics.enabled | bool | `false` | Deploy metrics service. |
| worker_async_api.metrics.service.annotations | object | `{}` | Metrics service annotations. |
| worker_async_api.metrics.service.labels | object | `{}` | Metrics service labels. |
| worker_async_api.metrics.service.port | int | `9000` | Metrics service port. |
| worker_async_api.metrics.service.portName | string | `"metrics"` | Metrics service port name. |
| worker_async_api.metrics.service.targetPort | int | `9000` | Metrics service target port. |
| worker_async_api.metrics.service.type | string | `"ClusterIP"` | Type of metrics service to create. |
| worker_async_api.metrics.serviceMonitor.annotations | object | `{}` | Prometheus ServiceMonitor annotations. |
| worker_async_api.metrics.serviceMonitor.enabled | bool | `false` | Enable a prometheus ServiceMonitor. |
| worker_async_api.metrics.serviceMonitor.endpoints[0].basicAuth.password | string | `""` | The secret in the service monitor namespace that contains the password for authentication. |
| worker_async_api.metrics.serviceMonitor.endpoints[0].basicAuth.username | string | `""` | The secret in the service monitor namespace that contains the username for authentication. |
| worker_async_api.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.key | string | `""` | Secret key to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| worker_async_api.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.name | string | `""` | Secret name to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| worker_async_api.metrics.serviceMonitor.endpoints[0].honorLabels | bool | `false` | When true, honorLabels preserves the metric’s labels when they collide with the target’s labels. |
| worker_async_api.metrics.serviceMonitor.endpoints[0].interval | string | `"30s"` | Prometheus ServiceMonitor interval. |
| worker_async_api.metrics.serviceMonitor.endpoints[0].metricRelabelings | list | `[]` | Prometheus MetricRelabelConfigs to apply to samples before ingestion. |
| worker_async_api.metrics.serviceMonitor.endpoints[0].path | string | `"/metrics"` | Path used by the Prometheus ServiceMonitor to scrape metrics. |
| worker_async_api.metrics.serviceMonitor.endpoints[0].relabelings | list | `[]` | Prometheus RelabelConfigs to apply to samples before scraping. |
| worker_async_api.metrics.serviceMonitor.endpoints[0].scheme | string | `""` | Prometheus ServiceMonitor scheme. |
| worker_async_api.metrics.serviceMonitor.endpoints[0].scrapeTimeout | string | `"10s"` | Prometheus ServiceMonitor scrapeTimeout. If empty, Prometheus uses the global scrape timeout unless it is less than the target's scrape interval value in which the latter is used. |
| worker_async_api.metrics.serviceMonitor.endpoints[0].selector | object | `{}` | Prometheus ServiceMonitor selector. |
| worker_async_api.metrics.serviceMonitor.endpoints[0].tlsConfig | object | `{}` | Prometheus ServiceMonitor tlsConfig. |
| worker_async_api.metrics.serviceMonitor.labels | object | `{}` | Prometheus ServiceMonitor labels. |

#### NetworkPolicy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_async_api.networkPolicy.annotations | object | `{}` | Annotations to be added to the app NetworkPolicy. |
| worker_async_api.networkPolicy.create | bool | `false` | Create NetworkPolicy object for the app. The policy always selects this component's pods only (via its selector labels), never the whole namespace. |
| worker_async_api.networkPolicy.egress | list | `[]` | Egress rules for the NetworkPolicy object. |
| worker_async_api.networkPolicy.ingress | list | `[]` | Ingress rules for the NetworkPolicy object. |
| worker_async_api.networkPolicy.labels | object | `{}` | Labels to be added to the app NetworkPolicy. |
| worker_async_api.networkPolicy.policyTypes | list | `["Ingress"]` | Policy types used in the NetworkPolicy object. |

#### Pdb

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_async_api.pdb.annotations | object | `{}` | Annotations to be added to app pdb. |
| worker_async_api.pdb.enabled | bool | `false` | Deploy a PodDisruptionBudget for the app |
| worker_async_api.pdb.labels | object | `{}` | Labels to be added to app pdb. |
| worker_async_api.pdb.maxUnavailable | string | `""` | Number of pods that are unavailable after eviction as number or percentage (eg.: 50%). Has higher precedence over `worker_async_api.pdb.minAvailable`. |
| worker_async_api.pdb.minAvailable | string | `""` | Number of pods that are available after eviction as number or percentage (eg.: 50%). One of `minAvailable` / `maxUnavailable` must be set when `pdb.enabled` is true - a budget of 0 is the same as having no budget at all, so leaving both empty fails at render time. |

#### Probes

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_async_api.probes.livenessProbe.failureThreshold | int | `3` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_async_api.probes.livenessProbe.httpGet.path | string | `"/health"` | Worker_async_api container healthcheck endpoint (livenessProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_async_api.probes.livenessProbe.httpGet.port | int | `8084` | Port to use for healthcheck (defaults to container port). |
| worker_async_api.probes.livenessProbe.initialDelaySeconds | int | `30` | Number of seconds after the container has started before probe is initiated. |
| worker_async_api.probes.livenessProbe.periodSeconds | int | `30` | How often (in seconds) to perform the probe. |
| worker_async_api.probes.livenessProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_async_api.probes.livenessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| worker_async_api.probes.readinessProbe.failureThreshold | int | `2` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_async_api.probes.readinessProbe.httpGet.path | string | `"/ready"` | Worker_async_api container healthcheck endpoint (readinessProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_async_api.probes.readinessProbe.httpGet.port | int | `8084` | Port to use for healthcheck (defaults to container port). |
| worker_async_api.probes.readinessProbe.initialDelaySeconds | int | `10` | Number of seconds after the container has started before probe is initiated. |
| worker_async_api.probes.readinessProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| worker_async_api.probes.readinessProbe.successThreshold | int | `2` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_async_api.probes.readinessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| worker_async_api.probes.startupProbe.failureThreshold | int | `10` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_async_api.probes.startupProbe.httpGet.path | string | `"/health"` | Worker_async_api container healthcheck endpoint (startupProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_async_api.probes.startupProbe.httpGet.port | int | `8084` | Port to use for healthcheck (defaults to container port). |
| worker_async_api.probes.startupProbe.initialDelaySeconds | int | `0` | Number of seconds after the container has started before probe is initiated. |
| worker_async_api.probes.startupProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| worker_async_api.probes.startupProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_async_api.probes.startupProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |

#### Resources

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_async_api.resources.limits.cpu | string | `"500m"` | CPU limit for the app. |
| worker_async_api.resources.limits.memory | string | `"2Gi"` | Memory limit for the app. |
| worker_async_api.resources.requests.cpu | string | `"100m"` | CPU request for the app. |
| worker_async_api.resources.requests.memory | string | `"256Mi"` | Memory request for the app. |

#### Service

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_async_api.service.enabled | bool | `false` | Whether or not to create a Service for the app. Set to `false` for components that don't accept traffic (e.g. a queue consumer with no `containerPort`). |
| worker_async_api.service.extraPorts | list | `[]` | Extra service ports. |
| worker_async_api.service.nodePort | int | `null` (allocated by Kubernetes) | Port used when type is `NodePort` to expose the service on the given node port. Left empty, Kubernetes allocates one from the configured node-port range, which avoids two releases of this chart colliding on the same hardcoded port. |
| worker_async_api.service.port | int | `80` | Port used by the service. |
| worker_async_api.service.portName | string | `"http"` | Port name used by the service. |
| worker_async_api.service.protocol | string | `"TCP"` | Protocol used by the service. |
| worker_async_api.service.type | string | `"ClusterIP"` | Type of service to create for the app. |

#### ServiceAccount

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_async_api.serviceAccount.annotations | object | `{}` | Annotations applied to created service account. |
| worker_async_api.serviceAccount.automountServiceAccountToken | bool | `false` | Should the service account access token be automount in the pod. |
| worker_async_api.serviceAccount.clusterRole.create | bool | `false` | Should the clusterRole be created. |
| worker_async_api.serviceAccount.clusterRole.rules | list | `[]` | ClusterRole rules associated with the service account. |
| worker_async_api.serviceAccount.create | bool | `false` | Create a service account. |
| worker_async_api.serviceAccount.enabled | bool | `false` | Enable the service account. |
| worker_async_api.serviceAccount.name | string | `""` | Service account name. |
| worker_async_api.serviceAccount.role.create | bool | `false` | Should the role be created. |
| worker_async_api.serviceAccount.role.rules | list | `[]` | Role rules associated with the service account. |

#### Strategy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_async_api.strategy.rollingUpdate.maxSurge | int | `1` | The maximum number of pods that can be scheduled above the desired number of pods. |
| worker_async_api.strategy.rollingUpdate.maxUnavailable | int | `1` | The maximum number of pods that can be unavailable during the update process. |
| worker_async_api.strategy.type | string | `"RollingUpdate"` | Strategy type used to replace old Pods by new ones, can be `Recreate` or `RollingUpdate`. Only applied when `deploymentType` is "Deployment". |

### WorkerClassification

#### General

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_classification.affinity | object | `{}` | Affinity used for app pod. |
| worker_classification.args | list | `[]` | Worker_classification container command args. |
| worker_classification.automountServiceAccountToken | bool | `false` | Mount the ServiceAccount token into the app pods. Defaults to false so a compromised container holds no API credentials; the API server does not need the token unless the app actually talks to the Kubernetes API. Applied at pod level so it holds even when `serviceAccount.name` points at an SA that automounts. |
| worker_classification.command | list | `[]` | Worker_classification container command. |
| worker_classification.containerPort | int | `8080` | Worker_classification container port number. Set to `null`/`0` (and disable `service`/probes) for components that don't listen on any port (e.g. a queue consumer). |
| worker_classification.containerPortName | string | `"http"` | Worker_classification container port name. |
| worker_classification.deploymentType | string | `"Deployment"` | Workload kind to deploy the app as. One of "Deployment", "StatefulSet" or "DaemonSet" (validated at render time - an unknown value fails instead of producing a release with no workload). Use the top-level `jobs` / `cronjobs` maps for one-off or scheduled workloads. Some values only apply to certain kinds: `replicaCount`/`autoscaling` and `strategy` are Deployment-only (`autoscaling` also works on a StatefulSet), `volumeClaims`/`extraVolumeClaims` are StatefulSet-only, and `updateStrategy` covers StatefulSet and DaemonSet. |
| worker_classification.dnsConfig | object | `{}` | Pod DNS configuration, merged with `dnsPolicy` by the kubelet. |
| worker_classification.dnsPolicy | string | `""` (`ClusterFirstWithHostNet` when `hostNetwork` is true) | Pod DNS policy. Left empty, it defaults to `ClusterFirstWithHostNet` when `hostNetwork` is true (otherwise a hostNetwork pod silently stops resolving cluster DNS) and to the Kubernetes default `ClusterFirst` when it isn't. |
| worker_classification.enableServiceLinks | bool | `false` | Inject the legacy `{SVC}_SERVICE_HOST`/`_PORT` environment variables for every Service in the namespace. Defaults to false: the variables are rarely used, leak the namespace's topology into every container, and can collide with the app's own configuration. Set to true only for an app that genuinely reads them. |
| worker_classification.env | object | `{}` | Map or array of environment variables to inject into the app container (`valueFrom` supported). |
| worker_classification.envCm | object | `{}` | Map of environment variables to inject into a configmap loaded by the app container (`valueFrom` not supported). |
| worker_classification.envFrom | list | `[]` | Worker_classification container env variables loaded from configmap or secret reference. List or map (merged with `global.envFrom` above, global entries first); see `global.envFrom` for both forms. |
| worker_classification.envSecret | object | `{}` | Map of environment variables to inject into a secret loaded by the app container (`valueFrom` not supported). Values placed here are stored in plain text in the values file AND in the Helm release secret, so use it for non-sensitive-but-secret-shaped config only. For real credentials prefer referencing a Secret you manage elsewhere via `envFrom`, or have an operator materialise it (see the `VaultStaticSecret` example under `extraObjects`). |
| worker_classification.extraContainers | list | `[]` | Extra containers to add to the app pod as sidecars. |
| worker_classification.extraPorts | list | `[]` | Worker_classification extra container ports. |
| worker_classification.extraVolumeClaims | list | `[]` | Additional volumeClaims to add, concatenated with `volumeClaims` above at render time. |
| worker_classification.extraVolumeMounts | list | `[]` | Additional volumeMounts to add, concatenated with `volumeMounts` above at render time. |
| worker_classification.extraVolumes | list | `[]` | Additional volumes to add, concatenated with `volumes` above at render time (e.g. to mount a cert or config from a values override without repeating the chart's own volumes). |
| worker_classification.hostAliases | list | `[]` | Host aliases that will be injected at pod-level into /etc/hosts. |
| worker_classification.hostNetwork | bool | `false` | Share the host network namespace. Container ports then bind directly on the node, so they must not collide with anything else running there. |
| worker_classification.hostPID | bool | `false` | Share the host PID namespace (lets the container see and signal host processes). |
| worker_classification.imagePullSecrets | list | `[]` | Image credentials configuration. |
| worker_classification.initContainers | list | `[]` | Init containers to add to the app pod. |
| worker_classification.nodeSelector | object | `{}` | Default node selector for app. |
| worker_classification.podAnnotations | object | `{}` | Annotations for the app deployed pods. |
| worker_classification.podLabels | object | `{}` | Labels for the app deployed pods. |
| worker_classification.podSecurityContext | object | `{"fsGroup":1000,"fsGroupChangePolicy":"OnRootMismatch","runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000,"seccompProfile":{"type":"RuntimeDefault"}}` | Pod-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard. Rendered via `toYaml`, so any `PodSecurityContext` field is accepted. Adjust the UID/GID to whatever your image actually ships with - `runAsNonRoot` makes the kubelet refuse to start a container that would run as root, which is the intended failure mode rather than something to switch off. Set to `null` to omit the block entirely. |
| worker_classification.priorityClassName | string | `""` | PriorityClass to schedule the pods with (e.g. `system-node-critical` for a node agent that must not be evicted under pressure). |
| worker_classification.replicaCount | int | `1` | The number of application controller pods to run. Ignored when `deploymentType` is "DaemonSet" (one pod per node) or when `autoscaling.enabled` is true. |
| worker_classification.revisionHistoryLimit | int | `10` | Revision history limit for the app. |
| worker_classification.securityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"privileged":false,"readOnlyRootFilesystem":true,"runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000}` | Container-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard: no privilege escalation, no capabilities, immutable root filesystem. Rendered via `toYaml`, so any `SecurityContext` field is accepted. Note `readOnlyRootFilesystem` requires the app to write only to mounted volumes - the default `volumes`/`volumeMounts` below provide an `emptyDir` on /tmp for that reason. Set to `null` to omit the block entirely. |
| worker_classification.terminationGracePeriodSeconds | int | `null` (Kubernetes default of 30) | Grace period, in seconds, given to the pod to shut down cleanly before it is killed. |
| worker_classification.tolerations | list | `[]` | Default tolerations for app. |
| worker_classification.topologySpreadConstraints | list | `[]` | Topology spread constraints used to spread the pods across failure domains. |
| worker_classification.updateStrategy | object | `{}` | Update strategy applied when `deploymentType` is "StatefulSet" or "DaemonSet" (ignored for a Deployment, which uses `strategy` above). Rendered verbatim via `toYaml`, so it takes the native `StatefulSetUpdateStrategy`/`DaemonSetUpdateStrategy` shape of the selected kind; left empty, Kubernetes applies its own default (`RollingUpdate` for both). |
| worker_classification.volumeClaims | list | `[]` | List of volumeClaims to add, rendered as the StatefulSet's `volumeClaimTemplates`. Requires `deploymentType: "StatefulSet"` - setting it on a Deployment or DaemonSet fails at render time rather than being silently dropped (use `volumes`/`extraVolumes` there instead). |
| worker_classification.volumeMounts | list | `[{"mountPath":"/tmp","name":"tmp"}]` | List of mounts to add (normally used with `volumes` or `volumeClaims`). Prefer this for mounts the chart itself always needs; use `extraVolumeMounts` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to the `/tmp` mount backing the hardened `readOnlyRootFilesystem` default (see `volumes` above). |
| worker_classification.volumes | list | `[{"emptyDir":{},"name":"tmp"}]` | List of volumes to add. Prefer this for volumes the chart itself always needs (e.g. security-hardening `emptyDir`s); use `extraVolumes` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to a `/tmp` `emptyDir`, which is what makes the default `securityContext.readOnlyRootFilesystem: true` usable - drop it only if you also relax that. Helm replaces lists wholesale rather than merging them, so overriding this key means restating the entries you want to keep. |

#### Autoscaling

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_classification.autoscaling.enabled | bool | `false` | Enable Horizontal Pod Autoscaler for the app. |
| worker_classification.autoscaling.maxReplicas | int | `3` | Maximum number of replicas for the app. |
| worker_classification.autoscaling.minReplicas | int | `1` | Minimum number of replicas for the app. |
| worker_classification.autoscaling.targetCPUUtilizationPercentage | int | `80` | Average CPU utilization percentage for the app. |
| worker_classification.autoscaling.targetMemoryUtilizationPercentage | int | `80` | Average memory utilization percentage for the app. |

#### GrpcRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_classification.grpcRoute.annotations | object | `{}` | Additional GRPCRoute annotations. |
| worker_classification.grpcRoute.enabled | bool | `false` | Enable a GRPCRoute resource for this service. |
| worker_classification.grpcRoute.hostnames | list | `[]` | Hostnames for the GRPCRoute to match. |
| worker_classification.grpcRoute.labels | object | `{}` | Additional GRPCRoute labels. |
| worker_classification.grpcRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the GRPCRoute to. |
| worker_classification.grpcRoute.rules | list | `[]` | Routing rules for the GRPCRoute. |

#### HttpRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_classification.httpRoute.annotations | object | `{}` | Additional HTTPRoute annotations. |
| worker_classification.httpRoute.enabled | bool | `false` | Enable an HTTPRoute resource for this service. |
| worker_classification.httpRoute.hostnames | list | `[]` | Hostnames for the HTTPRoute to match. |
| worker_classification.httpRoute.labels | object | `{}` | Additional HTTPRoute labels. |
| worker_classification.httpRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the HTTPRoute to. |
| worker_classification.httpRoute.rules | list | `[]` | Routing rules for the HTTPRoute. |

#### Image

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_classification.image.digest | string | `""` | Image digest (`sha256:...`). When set it takes precedence over `tag`, pinning the exact image content so the same release can never resolve to a different build - preferred over a mutable tag for anything you deploy to production. |
| worker_classification.image.pullPolicy | string | `"IfNotPresent"` | Image pull policy for the app. |
| worker_classification.image.registry | string | `"ghcr.io"` | Registry to use for the app. |
| worker_classification.image.repository | string | `"ia-generative/mille-feuille/worker-classification"` | Repository to use for the app. |
| worker_classification.image.tag | string | `""` | Tag to use for the app. Overrides the image tag whose default is the chart appVersion. |

#### Ingress

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_classification.ingress.annotations | object | `{}` | Additional ingress annotations. |
| worker_classification.ingress.className | string | `""` | Defines which ingress controller will implement the resource. |
| worker_classification.ingress.enabled | bool | `false` | Whether or not ingress should be enabled. |
| worker_classification.ingress.hosts[0].name | string | `"domain.local"` | Name of the host record. |
| worker_classification.ingress.hosts[0].paths | list | `[{"backend":{"portNumber":null,"serviceName":""},"path":"/","pathType":"Prefix"}]` | Paths of the host record to manage routing (avoids repeating the same host for multiple paths/backends). |
| worker_classification.ingress.hosts[0].paths[0].backend.portNumber | string | `nil` | Port used by the backend service linked to the path (leave null to use the app service port). |
| worker_classification.ingress.hosts[0].paths[0].backend.serviceName | string | `""` | Name of the backend service linked to the path (leave empty to use the app service). |
| worker_classification.ingress.hosts[0].paths[0].path | string | `"/"` | Path of the host record to manage routing. |
| worker_classification.ingress.hosts[0].paths[0].pathType | string | `"Prefix"` | Path type of the host record. |
| worker_classification.ingress.labels | object | `{}` | Additional ingress labels. |
| worker_classification.ingress.tls | list | `[]` | Enable TLS configuration. |

#### Metrics

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_classification.metrics.enabled | bool | `false` | Deploy metrics service. |
| worker_classification.metrics.service.annotations | object | `{}` | Metrics service annotations. |
| worker_classification.metrics.service.labels | object | `{}` | Metrics service labels. |
| worker_classification.metrics.service.port | int | `9000` | Metrics service port. |
| worker_classification.metrics.service.portName | string | `"metrics"` | Metrics service port name. |
| worker_classification.metrics.service.targetPort | int | `9000` | Metrics service target port. |
| worker_classification.metrics.service.type | string | `"ClusterIP"` | Type of metrics service to create. |
| worker_classification.metrics.serviceMonitor.annotations | object | `{}` | Prometheus ServiceMonitor annotations. |
| worker_classification.metrics.serviceMonitor.enabled | bool | `false` | Enable a prometheus ServiceMonitor. |
| worker_classification.metrics.serviceMonitor.endpoints[0].basicAuth.password | string | `""` | The secret in the service monitor namespace that contains the password for authentication. |
| worker_classification.metrics.serviceMonitor.endpoints[0].basicAuth.username | string | `""` | The secret in the service monitor namespace that contains the username for authentication. |
| worker_classification.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.key | string | `""` | Secret key to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| worker_classification.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.name | string | `""` | Secret name to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| worker_classification.metrics.serviceMonitor.endpoints[0].honorLabels | bool | `false` | When true, honorLabels preserves the metric’s labels when they collide with the target’s labels. |
| worker_classification.metrics.serviceMonitor.endpoints[0].interval | string | `"30s"` | Prometheus ServiceMonitor interval. |
| worker_classification.metrics.serviceMonitor.endpoints[0].metricRelabelings | list | `[]` | Prometheus MetricRelabelConfigs to apply to samples before ingestion. |
| worker_classification.metrics.serviceMonitor.endpoints[0].path | string | `"/metrics"` | Path used by the Prometheus ServiceMonitor to scrape metrics. |
| worker_classification.metrics.serviceMonitor.endpoints[0].relabelings | list | `[]` | Prometheus RelabelConfigs to apply to samples before scraping. |
| worker_classification.metrics.serviceMonitor.endpoints[0].scheme | string | `""` | Prometheus ServiceMonitor scheme. |
| worker_classification.metrics.serviceMonitor.endpoints[0].scrapeTimeout | string | `"10s"` | Prometheus ServiceMonitor scrapeTimeout. If empty, Prometheus uses the global scrape timeout unless it is less than the target's scrape interval value in which the latter is used. |
| worker_classification.metrics.serviceMonitor.endpoints[0].selector | object | `{}` | Prometheus ServiceMonitor selector. |
| worker_classification.metrics.serviceMonitor.endpoints[0].tlsConfig | object | `{}` | Prometheus ServiceMonitor tlsConfig. |
| worker_classification.metrics.serviceMonitor.labels | object | `{}` | Prometheus ServiceMonitor labels. |

#### NetworkPolicy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_classification.networkPolicy.annotations | object | `{}` | Annotations to be added to the app NetworkPolicy. |
| worker_classification.networkPolicy.create | bool | `false` | Create NetworkPolicy object for the app. The policy always selects this component's pods only (via its selector labels), never the whole namespace. |
| worker_classification.networkPolicy.egress | list | `[]` | Egress rules for the NetworkPolicy object. |
| worker_classification.networkPolicy.ingress | list | `[]` | Ingress rules for the NetworkPolicy object. |
| worker_classification.networkPolicy.labels | object | `{}` | Labels to be added to the app NetworkPolicy. |
| worker_classification.networkPolicy.policyTypes | list | `["Ingress"]` | Policy types used in the NetworkPolicy object. |

#### Pdb

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_classification.pdb.annotations | object | `{}` | Annotations to be added to app pdb. |
| worker_classification.pdb.enabled | bool | `false` | Deploy a PodDisruptionBudget for the app |
| worker_classification.pdb.labels | object | `{}` | Labels to be added to app pdb. |
| worker_classification.pdb.maxUnavailable | string | `""` | Number of pods that are unavailable after eviction as number or percentage (eg.: 50%). Has higher precedence over `worker_classification.pdb.minAvailable`. |
| worker_classification.pdb.minAvailable | string | `""` | Number of pods that are available after eviction as number or percentage (eg.: 50%). One of `minAvailable` / `maxUnavailable` must be set when `pdb.enabled` is true - a budget of 0 is the same as having no budget at all, so leaving both empty fails at render time. |

#### Probes

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_classification.probes.livenessProbe.failureThreshold | int | `3` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_classification.probes.livenessProbe.httpGet.path | string | `"/"` | Worker_classification container healthcheck endpoint (livenessProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_classification.probes.livenessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_classification.probes.livenessProbe.initialDelaySeconds | int | `30` | Number of seconds after the container has started before probe is initiated. |
| worker_classification.probes.livenessProbe.periodSeconds | int | `30` | How often (in seconds) to perform the probe. |
| worker_classification.probes.livenessProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_classification.probes.livenessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| worker_classification.probes.readinessProbe.failureThreshold | int | `2` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_classification.probes.readinessProbe.httpGet.path | string | `"/"` | Worker_classification container healthcheck endpoint (readinessProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_classification.probes.readinessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_classification.probes.readinessProbe.initialDelaySeconds | int | `10` | Number of seconds after the container has started before probe is initiated. |
| worker_classification.probes.readinessProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| worker_classification.probes.readinessProbe.successThreshold | int | `2` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_classification.probes.readinessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| worker_classification.probes.startupProbe.failureThreshold | int | `10` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_classification.probes.startupProbe.httpGet.path | string | `"/"` | Worker_classification container healthcheck endpoint (startupProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_classification.probes.startupProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_classification.probes.startupProbe.initialDelaySeconds | int | `0` | Number of seconds after the container has started before probe is initiated. |
| worker_classification.probes.startupProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| worker_classification.probes.startupProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_classification.probes.startupProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |

#### Resources

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_classification.resources.limits.cpu | string | `"500m"` | CPU limit for the app. |
| worker_classification.resources.limits.memory | string | `"2Gi"` | Memory limit for the app. |
| worker_classification.resources.requests.cpu | string | `"100m"` | CPU request for the app. |
| worker_classification.resources.requests.memory | string | `"256Mi"` | Memory request for the app. |

#### Service

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_classification.service.enabled | bool | `true` | Whether or not to create a Service for the app. Set to `false` for components that don't accept traffic (e.g. a queue consumer with no `containerPort`). |
| worker_classification.service.extraPorts | list | `[]` | Extra service ports. |
| worker_classification.service.nodePort | int | `null` (allocated by Kubernetes) | Port used when type is `NodePort` to expose the service on the given node port. Left empty, Kubernetes allocates one from the configured node-port range, which avoids two releases of this chart colliding on the same hardcoded port. |
| worker_classification.service.port | int | `80` | Port used by the service. |
| worker_classification.service.portName | string | `"http"` | Port name used by the service. |
| worker_classification.service.protocol | string | `"TCP"` | Protocol used by the service. |
| worker_classification.service.type | string | `"ClusterIP"` | Type of service to create for the app. |

#### ServiceAccount

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_classification.serviceAccount.annotations | object | `{}` | Annotations applied to created service account. |
| worker_classification.serviceAccount.automountServiceAccountToken | bool | `false` | Should the service account access token be automount in the pod. |
| worker_classification.serviceAccount.clusterRole.create | bool | `false` | Should the clusterRole be created. |
| worker_classification.serviceAccount.clusterRole.rules | list | `[]` | ClusterRole rules associated with the service account. |
| worker_classification.serviceAccount.create | bool | `false` | Create a service account. |
| worker_classification.serviceAccount.enabled | bool | `false` | Enable the service account. |
| worker_classification.serviceAccount.name | string | `""` | Service account name. |
| worker_classification.serviceAccount.role.create | bool | `false` | Should the role be created. |
| worker_classification.serviceAccount.role.rules | list | `[]` | Role rules associated with the service account. |

#### Strategy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_classification.strategy.rollingUpdate.maxSurge | int | `1` | The maximum number of pods that can be scheduled above the desired number of pods. |
| worker_classification.strategy.rollingUpdate.maxUnavailable | int | `1` | The maximum number of pods that can be unavailable during the update process. |
| worker_classification.strategy.type | string | `"RollingUpdate"` | Strategy type used to replace old Pods by new ones, can be `Recreate` or `RollingUpdate`. Only applied when `deploymentType` is "Deployment". |

### WorkerDocument

#### General

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_document.affinity | object | `{}` | Affinity used for app pod. |
| worker_document.args | list | `[]` | Worker_document container command args. |
| worker_document.automountServiceAccountToken | bool | `false` | Mount the ServiceAccount token into the app pods. Defaults to false so a compromised container holds no API credentials; the API server does not need the token unless the app actually talks to the Kubernetes API. Applied at pod level so it holds even when `serviceAccount.name` points at an SA that automounts. |
| worker_document.command | list | `[]` | Worker_document container command. |
| worker_document.containerPort | int | `8080` | Worker_document container port number. Set to `null`/`0` (and disable `service`/probes) for components that don't listen on any port (e.g. a queue consumer). |
| worker_document.containerPortName | string | `"http"` | Worker_document container port name. |
| worker_document.deploymentType | string | `"Deployment"` | Workload kind to deploy the app as. One of "Deployment", "StatefulSet" or "DaemonSet" (validated at render time - an unknown value fails instead of producing a release with no workload). Use the top-level `jobs` / `cronjobs` maps for one-off or scheduled workloads. Some values only apply to certain kinds: `replicaCount`/`autoscaling` and `strategy` are Deployment-only (`autoscaling` also works on a StatefulSet), `volumeClaims`/`extraVolumeClaims` are StatefulSet-only, and `updateStrategy` covers StatefulSet and DaemonSet. |
| worker_document.dnsConfig | object | `{}` | Pod DNS configuration, merged with `dnsPolicy` by the kubelet. |
| worker_document.dnsPolicy | string | `""` (`ClusterFirstWithHostNet` when `hostNetwork` is true) | Pod DNS policy. Left empty, it defaults to `ClusterFirstWithHostNet` when `hostNetwork` is true (otherwise a hostNetwork pod silently stops resolving cluster DNS) and to the Kubernetes default `ClusterFirst` when it isn't. |
| worker_document.enableServiceLinks | bool | `false` | Inject the legacy `{SVC}_SERVICE_HOST`/`_PORT` environment variables for every Service in the namespace. Defaults to false: the variables are rarely used, leak the namespace's topology into every container, and can collide with the app's own configuration. Set to true only for an app that genuinely reads them. |
| worker_document.env | object | `{}` | Map or array of environment variables to inject into the app container (`valueFrom` supported). |
| worker_document.envCm | object | `{}` | Map of environment variables to inject into a configmap loaded by the app container (`valueFrom` not supported). |
| worker_document.envFrom | list | `[]` | Worker_document container env variables loaded from configmap or secret reference. List or map (merged with `global.envFrom` above, global entries first); see `global.envFrom` for both forms. |
| worker_document.envSecret | object | `{}` | Map of environment variables to inject into a secret loaded by the app container (`valueFrom` not supported). Values placed here are stored in plain text in the values file AND in the Helm release secret, so use it for non-sensitive-but-secret-shaped config only. For real credentials prefer referencing a Secret you manage elsewhere via `envFrom`, or have an operator materialise it (see the `VaultStaticSecret` example under `extraObjects`). |
| worker_document.extraContainers | list | `[]` | Extra containers to add to the app pod as sidecars. |
| worker_document.extraPorts | list | `[]` | Worker_document extra container ports. |
| worker_document.extraVolumeClaims | list | `[]` | Additional volumeClaims to add, concatenated with `volumeClaims` above at render time. |
| worker_document.extraVolumeMounts | list | `[]` | Additional volumeMounts to add, concatenated with `volumeMounts` above at render time. |
| worker_document.extraVolumes | list | `[]` | Additional volumes to add, concatenated with `volumes` above at render time (e.g. to mount a cert or config from a values override without repeating the chart's own volumes). |
| worker_document.hostAliases | list | `[]` | Host aliases that will be injected at pod-level into /etc/hosts. |
| worker_document.hostNetwork | bool | `false` | Share the host network namespace. Container ports then bind directly on the node, so they must not collide with anything else running there. |
| worker_document.hostPID | bool | `false` | Share the host PID namespace (lets the container see and signal host processes). |
| worker_document.imagePullSecrets | list | `[]` | Image credentials configuration. |
| worker_document.initContainers | list | `[]` | Init containers to add to the app pod. |
| worker_document.nodeSelector | object | `{}` | Default node selector for app. |
| worker_document.podAnnotations | object | `{}` | Annotations for the app deployed pods. |
| worker_document.podLabels | object | `{}` | Labels for the app deployed pods. |
| worker_document.podSecurityContext | object | `{"fsGroup":1000,"fsGroupChangePolicy":"OnRootMismatch","runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000,"seccompProfile":{"type":"RuntimeDefault"}}` | Pod-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard. Rendered via `toYaml`, so any `PodSecurityContext` field is accepted. Adjust the UID/GID to whatever your image actually ships with - `runAsNonRoot` makes the kubelet refuse to start a container that would run as root, which is the intended failure mode rather than something to switch off. Set to `null` to omit the block entirely. |
| worker_document.priorityClassName | string | `""` | PriorityClass to schedule the pods with (e.g. `system-node-critical` for a node agent that must not be evicted under pressure). |
| worker_document.replicaCount | int | `1` | The number of application controller pods to run. Ignored when `deploymentType` is "DaemonSet" (one pod per node) or when `autoscaling.enabled` is true. |
| worker_document.revisionHistoryLimit | int | `10` | Revision history limit for the app. |
| worker_document.securityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"privileged":false,"readOnlyRootFilesystem":true,"runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000}` | Container-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard: no privilege escalation, no capabilities, immutable root filesystem. Rendered via `toYaml`, so any `SecurityContext` field is accepted. Note `readOnlyRootFilesystem` requires the app to write only to mounted volumes - the default `volumes`/`volumeMounts` below provide an `emptyDir` on /tmp for that reason. Set to `null` to omit the block entirely. |
| worker_document.terminationGracePeriodSeconds | int | `null` (Kubernetes default of 30) | Grace period, in seconds, given to the pod to shut down cleanly before it is killed. |
| worker_document.tolerations | list | `[]` | Default tolerations for app. |
| worker_document.topologySpreadConstraints | list | `[]` | Topology spread constraints used to spread the pods across failure domains. |
| worker_document.updateStrategy | object | `{}` | Update strategy applied when `deploymentType` is "StatefulSet" or "DaemonSet" (ignored for a Deployment, which uses `strategy` above). Rendered verbatim via `toYaml`, so it takes the native `StatefulSetUpdateStrategy`/`DaemonSetUpdateStrategy` shape of the selected kind; left empty, Kubernetes applies its own default (`RollingUpdate` for both). |
| worker_document.volumeClaims | list | `[]` | List of volumeClaims to add, rendered as the StatefulSet's `volumeClaimTemplates`. Requires `deploymentType: "StatefulSet"` - setting it on a Deployment or DaemonSet fails at render time rather than being silently dropped (use `volumes`/`extraVolumes` there instead). |
| worker_document.volumeMounts | list | `[{"mountPath":"/tmp","name":"tmp"}]` | List of mounts to add (normally used with `volumes` or `volumeClaims`). Prefer this for mounts the chart itself always needs; use `extraVolumeMounts` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to the `/tmp` mount backing the hardened `readOnlyRootFilesystem` default (see `volumes` above). |
| worker_document.volumes | list | `[{"emptyDir":{},"name":"tmp"}]` | List of volumes to add. Prefer this for volumes the chart itself always needs (e.g. security-hardening `emptyDir`s); use `extraVolumes` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to a `/tmp` `emptyDir`, which is what makes the default `securityContext.readOnlyRootFilesystem: true` usable - drop it only if you also relax that. Helm replaces lists wholesale rather than merging them, so overriding this key means restating the entries you want to keep. |

#### Autoscaling

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_document.autoscaling.enabled | bool | `false` | Enable Horizontal Pod Autoscaler for the app. |
| worker_document.autoscaling.maxReplicas | int | `3` | Maximum number of replicas for the app. |
| worker_document.autoscaling.minReplicas | int | `1` | Minimum number of replicas for the app. |
| worker_document.autoscaling.targetCPUUtilizationPercentage | int | `80` | Average CPU utilization percentage for the app. |
| worker_document.autoscaling.targetMemoryUtilizationPercentage | int | `80` | Average memory utilization percentage for the app. |

#### GrpcRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_document.grpcRoute.annotations | object | `{}` | Additional GRPCRoute annotations. |
| worker_document.grpcRoute.enabled | bool | `false` | Enable a GRPCRoute resource for this service. |
| worker_document.grpcRoute.hostnames | list | `[]` | Hostnames for the GRPCRoute to match. |
| worker_document.grpcRoute.labels | object | `{}` | Additional GRPCRoute labels. |
| worker_document.grpcRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the GRPCRoute to. |
| worker_document.grpcRoute.rules | list | `[]` | Routing rules for the GRPCRoute. |

#### HttpRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_document.httpRoute.annotations | object | `{}` | Additional HTTPRoute annotations. |
| worker_document.httpRoute.enabled | bool | `false` | Enable an HTTPRoute resource for this service. |
| worker_document.httpRoute.hostnames | list | `[]` | Hostnames for the HTTPRoute to match. |
| worker_document.httpRoute.labels | object | `{}` | Additional HTTPRoute labels. |
| worker_document.httpRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the HTTPRoute to. |
| worker_document.httpRoute.rules | list | `[]` | Routing rules for the HTTPRoute. |

#### Image

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_document.image.digest | string | `""` | Image digest (`sha256:...`). When set it takes precedence over `tag`, pinning the exact image content so the same release can never resolve to a different build - preferred over a mutable tag for anything you deploy to production. |
| worker_document.image.pullPolicy | string | `"IfNotPresent"` | Image pull policy for the app. |
| worker_document.image.registry | string | `"ghcr.io"` | Registry to use for the app. |
| worker_document.image.repository | string | `"ia-generative/mille-feuille/worker-document-process"` | Repository to use for the app. |
| worker_document.image.tag | string | `""` | Tag to use for the app. Overrides the image tag whose default is the chart appVersion. |

#### Ingress

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_document.ingress.annotations | object | `{}` | Additional ingress annotations. |
| worker_document.ingress.className | string | `""` | Defines which ingress controller will implement the resource. |
| worker_document.ingress.enabled | bool | `false` | Whether or not ingress should be enabled. |
| worker_document.ingress.hosts[0].name | string | `"domain.local"` | Name of the host record. |
| worker_document.ingress.hosts[0].paths | list | `[{"backend":{"portNumber":null,"serviceName":""},"path":"/","pathType":"Prefix"}]` | Paths of the host record to manage routing (avoids repeating the same host for multiple paths/backends). |
| worker_document.ingress.hosts[0].paths[0].backend.portNumber | string | `nil` | Port used by the backend service linked to the path (leave null to use the app service port). |
| worker_document.ingress.hosts[0].paths[0].backend.serviceName | string | `""` | Name of the backend service linked to the path (leave empty to use the app service). |
| worker_document.ingress.hosts[0].paths[0].path | string | `"/"` | Path of the host record to manage routing. |
| worker_document.ingress.hosts[0].paths[0].pathType | string | `"Prefix"` | Path type of the host record. |
| worker_document.ingress.labels | object | `{}` | Additional ingress labels. |
| worker_document.ingress.tls | list | `[]` | Enable TLS configuration. |

#### Metrics

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_document.metrics.enabled | bool | `false` | Deploy metrics service. |
| worker_document.metrics.service.annotations | object | `{}` | Metrics service annotations. |
| worker_document.metrics.service.labels | object | `{}` | Metrics service labels. |
| worker_document.metrics.service.port | int | `9000` | Metrics service port. |
| worker_document.metrics.service.portName | string | `"metrics"` | Metrics service port name. |
| worker_document.metrics.service.targetPort | int | `9000` | Metrics service target port. |
| worker_document.metrics.service.type | string | `"ClusterIP"` | Type of metrics service to create. |
| worker_document.metrics.serviceMonitor.annotations | object | `{}` | Prometheus ServiceMonitor annotations. |
| worker_document.metrics.serviceMonitor.enabled | bool | `false` | Enable a prometheus ServiceMonitor. |
| worker_document.metrics.serviceMonitor.endpoints[0].basicAuth.password | string | `""` | The secret in the service monitor namespace that contains the password for authentication. |
| worker_document.metrics.serviceMonitor.endpoints[0].basicAuth.username | string | `""` | The secret in the service monitor namespace that contains the username for authentication. |
| worker_document.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.key | string | `""` | Secret key to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| worker_document.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.name | string | `""` | Secret name to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| worker_document.metrics.serviceMonitor.endpoints[0].honorLabels | bool | `false` | When true, honorLabels preserves the metric’s labels when they collide with the target’s labels. |
| worker_document.metrics.serviceMonitor.endpoints[0].interval | string | `"30s"` | Prometheus ServiceMonitor interval. |
| worker_document.metrics.serviceMonitor.endpoints[0].metricRelabelings | list | `[]` | Prometheus MetricRelabelConfigs to apply to samples before ingestion. |
| worker_document.metrics.serviceMonitor.endpoints[0].path | string | `"/metrics"` | Path used by the Prometheus ServiceMonitor to scrape metrics. |
| worker_document.metrics.serviceMonitor.endpoints[0].relabelings | list | `[]` | Prometheus RelabelConfigs to apply to samples before scraping. |
| worker_document.metrics.serviceMonitor.endpoints[0].scheme | string | `""` | Prometheus ServiceMonitor scheme. |
| worker_document.metrics.serviceMonitor.endpoints[0].scrapeTimeout | string | `"10s"` | Prometheus ServiceMonitor scrapeTimeout. If empty, Prometheus uses the global scrape timeout unless it is less than the target's scrape interval value in which the latter is used. |
| worker_document.metrics.serviceMonitor.endpoints[0].selector | object | `{}` | Prometheus ServiceMonitor selector. |
| worker_document.metrics.serviceMonitor.endpoints[0].tlsConfig | object | `{}` | Prometheus ServiceMonitor tlsConfig. |
| worker_document.metrics.serviceMonitor.labels | object | `{}` | Prometheus ServiceMonitor labels. |

#### NetworkPolicy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_document.networkPolicy.annotations | object | `{}` | Annotations to be added to the app NetworkPolicy. |
| worker_document.networkPolicy.create | bool | `false` | Create NetworkPolicy object for the app. The policy always selects this component's pods only (via its selector labels), never the whole namespace. |
| worker_document.networkPolicy.egress | list | `[]` | Egress rules for the NetworkPolicy object. |
| worker_document.networkPolicy.ingress | list | `[]` | Ingress rules for the NetworkPolicy object. |
| worker_document.networkPolicy.labels | object | `{}` | Labels to be added to the app NetworkPolicy. |
| worker_document.networkPolicy.policyTypes | list | `["Ingress"]` | Policy types used in the NetworkPolicy object. |

#### Pdb

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_document.pdb.annotations | object | `{}` | Annotations to be added to app pdb. |
| worker_document.pdb.enabled | bool | `false` | Deploy a PodDisruptionBudget for the app |
| worker_document.pdb.labels | object | `{}` | Labels to be added to app pdb. |
| worker_document.pdb.maxUnavailable | string | `""` | Number of pods that are unavailable after eviction as number or percentage (eg.: 50%). Has higher precedence over `worker_document.pdb.minAvailable`. |
| worker_document.pdb.minAvailable | string | `""` | Number of pods that are available after eviction as number or percentage (eg.: 50%). One of `minAvailable` / `maxUnavailable` must be set when `pdb.enabled` is true - a budget of 0 is the same as having no budget at all, so leaving both empty fails at render time. |

#### Probes

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_document.probes.livenessProbe.failureThreshold | int | `3` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_document.probes.livenessProbe.httpGet.path | string | `"/"` | Worker_document container healthcheck endpoint (livenessProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_document.probes.livenessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_document.probes.livenessProbe.initialDelaySeconds | int | `30` | Number of seconds after the container has started before probe is initiated. |
| worker_document.probes.livenessProbe.periodSeconds | int | `30` | How often (in seconds) to perform the probe. |
| worker_document.probes.livenessProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_document.probes.livenessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| worker_document.probes.readinessProbe.failureThreshold | int | `2` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_document.probes.readinessProbe.httpGet.path | string | `"/"` | Worker_document container healthcheck endpoint (readinessProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_document.probes.readinessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_document.probes.readinessProbe.initialDelaySeconds | int | `10` | Number of seconds after the container has started before probe is initiated. |
| worker_document.probes.readinessProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| worker_document.probes.readinessProbe.successThreshold | int | `2` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_document.probes.readinessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| worker_document.probes.startupProbe.failureThreshold | int | `10` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_document.probes.startupProbe.httpGet.path | string | `"/"` | Worker_document container healthcheck endpoint (startupProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_document.probes.startupProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_document.probes.startupProbe.initialDelaySeconds | int | `0` | Number of seconds after the container has started before probe is initiated. |
| worker_document.probes.startupProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| worker_document.probes.startupProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_document.probes.startupProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |

#### Resources

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_document.resources.limits.cpu | string | `"500m"` | CPU limit for the app. |
| worker_document.resources.limits.memory | string | `"2Gi"` | Memory limit for the app. |
| worker_document.resources.requests.cpu | string | `"100m"` | CPU request for the app. |
| worker_document.resources.requests.memory | string | `"256Mi"` | Memory request for the app. |

#### Service

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_document.service.enabled | bool | `true` | Whether or not to create a Service for the app. Set to `false` for components that don't accept traffic (e.g. a queue consumer with no `containerPort`). |
| worker_document.service.extraPorts | list | `[]` | Extra service ports. |
| worker_document.service.nodePort | int | `null` (allocated by Kubernetes) | Port used when type is `NodePort` to expose the service on the given node port. Left empty, Kubernetes allocates one from the configured node-port range, which avoids two releases of this chart colliding on the same hardcoded port. |
| worker_document.service.port | int | `80` | Port used by the service. |
| worker_document.service.portName | string | `"http"` | Port name used by the service. |
| worker_document.service.protocol | string | `"TCP"` | Protocol used by the service. |
| worker_document.service.type | string | `"ClusterIP"` | Type of service to create for the app. |

#### ServiceAccount

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_document.serviceAccount.annotations | object | `{}` | Annotations applied to created service account. |
| worker_document.serviceAccount.automountServiceAccountToken | bool | `false` | Should the service account access token be automount in the pod. |
| worker_document.serviceAccount.clusterRole.create | bool | `false` | Should the clusterRole be created. |
| worker_document.serviceAccount.clusterRole.rules | list | `[]` | ClusterRole rules associated with the service account. |
| worker_document.serviceAccount.create | bool | `false` | Create a service account. |
| worker_document.serviceAccount.enabled | bool | `false` | Enable the service account. |
| worker_document.serviceAccount.name | string | `""` | Service account name. |
| worker_document.serviceAccount.role.create | bool | `false` | Should the role be created. |
| worker_document.serviceAccount.role.rules | list | `[]` | Role rules associated with the service account. |

#### Strategy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_document.strategy.rollingUpdate.maxSurge | int | `1` | The maximum number of pods that can be scheduled above the desired number of pods. |
| worker_document.strategy.rollingUpdate.maxUnavailable | int | `1` | The maximum number of pods that can be unavailable during the update process. |
| worker_document.strategy.type | string | `"RollingUpdate"` | Strategy type used to replace old Pods by new ones, can be `Recreate` or `RollingUpdate`. Only applied when `deploymentType` is "Deployment". |

### WorkerExtraction

#### General

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_extraction.affinity | object | `{}` | Affinity used for app pod. |
| worker_extraction.args | list | `[]` | Worker_extraction container command args. |
| worker_extraction.automountServiceAccountToken | bool | `false` | Mount the ServiceAccount token into the app pods. Defaults to false so a compromised container holds no API credentials; the API server does not need the token unless the app actually talks to the Kubernetes API. Applied at pod level so it holds even when `serviceAccount.name` points at an SA that automounts. |
| worker_extraction.command | list | `[]` | Worker_extraction container command. |
| worker_extraction.containerPort | int | `8080` | Worker_extraction container port number. Set to `null`/`0` (and disable `service`/probes) for components that don't listen on any port (e.g. a queue consumer). |
| worker_extraction.containerPortName | string | `"http"` | Worker_extraction container port name. |
| worker_extraction.deploymentType | string | `"Deployment"` | Workload kind to deploy the app as. One of "Deployment", "StatefulSet" or "DaemonSet" (validated at render time - an unknown value fails instead of producing a release with no workload). Use the top-level `jobs` / `cronjobs` maps for one-off or scheduled workloads. Some values only apply to certain kinds: `replicaCount`/`autoscaling` and `strategy` are Deployment-only (`autoscaling` also works on a StatefulSet), `volumeClaims`/`extraVolumeClaims` are StatefulSet-only, and `updateStrategy` covers StatefulSet and DaemonSet. |
| worker_extraction.dnsConfig | object | `{}` | Pod DNS configuration, merged with `dnsPolicy` by the kubelet. |
| worker_extraction.dnsPolicy | string | `""` (`ClusterFirstWithHostNet` when `hostNetwork` is true) | Pod DNS policy. Left empty, it defaults to `ClusterFirstWithHostNet` when `hostNetwork` is true (otherwise a hostNetwork pod silently stops resolving cluster DNS) and to the Kubernetes default `ClusterFirst` when it isn't. |
| worker_extraction.enableServiceLinks | bool | `false` | Inject the legacy `{SVC}_SERVICE_HOST`/`_PORT` environment variables for every Service in the namespace. Defaults to false: the variables are rarely used, leak the namespace's topology into every container, and can collide with the app's own configuration. Set to true only for an app that genuinely reads them. |
| worker_extraction.env | object | `{}` | Map or array of environment variables to inject into the app container (`valueFrom` supported). |
| worker_extraction.envCm | object | `{}` | Map of environment variables to inject into a configmap loaded by the app container (`valueFrom` not supported). |
| worker_extraction.envFrom | list | `[]` | Worker_extraction container env variables loaded from configmap or secret reference. List or map (merged with `global.envFrom` above, global entries first); see `global.envFrom` for both forms. |
| worker_extraction.envSecret | object | `{}` | Map of environment variables to inject into a secret loaded by the app container (`valueFrom` not supported). Values placed here are stored in plain text in the values file AND in the Helm release secret, so use it for non-sensitive-but-secret-shaped config only. For real credentials prefer referencing a Secret you manage elsewhere via `envFrom`, or have an operator materialise it (see the `VaultStaticSecret` example under `extraObjects`). |
| worker_extraction.extraContainers | list | `[]` | Extra containers to add to the app pod as sidecars. |
| worker_extraction.extraPorts | list | `[]` | Worker_extraction extra container ports. |
| worker_extraction.extraVolumeClaims | list | `[]` | Additional volumeClaims to add, concatenated with `volumeClaims` above at render time. |
| worker_extraction.extraVolumeMounts | list | `[]` | Additional volumeMounts to add, concatenated with `volumeMounts` above at render time. |
| worker_extraction.extraVolumes | list | `[]` | Additional volumes to add, concatenated with `volumes` above at render time (e.g. to mount a cert or config from a values override without repeating the chart's own volumes). |
| worker_extraction.hostAliases | list | `[]` | Host aliases that will be injected at pod-level into /etc/hosts. |
| worker_extraction.hostNetwork | bool | `false` | Share the host network namespace. Container ports then bind directly on the node, so they must not collide with anything else running there. |
| worker_extraction.hostPID | bool | `false` | Share the host PID namespace (lets the container see and signal host processes). |
| worker_extraction.imagePullSecrets | list | `[]` | Image credentials configuration. |
| worker_extraction.initContainers | list | `[]` | Init containers to add to the app pod. |
| worker_extraction.nodeSelector | object | `{}` | Default node selector for app. |
| worker_extraction.podAnnotations | object | `{}` | Annotations for the app deployed pods. |
| worker_extraction.podLabels | object | `{}` | Labels for the app deployed pods. |
| worker_extraction.podSecurityContext | object | `{"fsGroup":1000,"fsGroupChangePolicy":"OnRootMismatch","runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000,"seccompProfile":{"type":"RuntimeDefault"}}` | Pod-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard. Rendered via `toYaml`, so any `PodSecurityContext` field is accepted. Adjust the UID/GID to whatever your image actually ships with - `runAsNonRoot` makes the kubelet refuse to start a container that would run as root, which is the intended failure mode rather than something to switch off. Set to `null` to omit the block entirely. |
| worker_extraction.priorityClassName | string | `""` | PriorityClass to schedule the pods with (e.g. `system-node-critical` for a node agent that must not be evicted under pressure). |
| worker_extraction.replicaCount | int | `1` | The number of application controller pods to run. Ignored when `deploymentType` is "DaemonSet" (one pod per node) or when `autoscaling.enabled` is true. |
| worker_extraction.revisionHistoryLimit | int | `10` | Revision history limit for the app. |
| worker_extraction.securityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"privileged":false,"readOnlyRootFilesystem":true,"runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000}` | Container-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard: no privilege escalation, no capabilities, immutable root filesystem. Rendered via `toYaml`, so any `SecurityContext` field is accepted. Note `readOnlyRootFilesystem` requires the app to write only to mounted volumes - the default `volumes`/`volumeMounts` below provide an `emptyDir` on /tmp for that reason. Set to `null` to omit the block entirely. |
| worker_extraction.terminationGracePeriodSeconds | int | `null` (Kubernetes default of 30) | Grace period, in seconds, given to the pod to shut down cleanly before it is killed. |
| worker_extraction.tolerations | list | `[]` | Default tolerations for app. |
| worker_extraction.topologySpreadConstraints | list | `[]` | Topology spread constraints used to spread the pods across failure domains. |
| worker_extraction.updateStrategy | object | `{}` | Update strategy applied when `deploymentType` is "StatefulSet" or "DaemonSet" (ignored for a Deployment, which uses `strategy` above). Rendered verbatim via `toYaml`, so it takes the native `StatefulSetUpdateStrategy`/`DaemonSetUpdateStrategy` shape of the selected kind; left empty, Kubernetes applies its own default (`RollingUpdate` for both). |
| worker_extraction.volumeClaims | list | `[]` | List of volumeClaims to add, rendered as the StatefulSet's `volumeClaimTemplates`. Requires `deploymentType: "StatefulSet"` - setting it on a Deployment or DaemonSet fails at render time rather than being silently dropped (use `volumes`/`extraVolumes` there instead). |
| worker_extraction.volumeMounts | list | `[{"mountPath":"/tmp","name":"tmp"}]` | List of mounts to add (normally used with `volumes` or `volumeClaims`). Prefer this for mounts the chart itself always needs; use `extraVolumeMounts` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to the `/tmp` mount backing the hardened `readOnlyRootFilesystem` default (see `volumes` above). |
| worker_extraction.volumes | list | `[{"emptyDir":{},"name":"tmp"}]` | List of volumes to add. Prefer this for volumes the chart itself always needs (e.g. security-hardening `emptyDir`s); use `extraVolumes` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to a `/tmp` `emptyDir`, which is what makes the default `securityContext.readOnlyRootFilesystem: true` usable - drop it only if you also relax that. Helm replaces lists wholesale rather than merging them, so overriding this key means restating the entries you want to keep. |

#### Autoscaling

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_extraction.autoscaling.enabled | bool | `false` | Enable Horizontal Pod Autoscaler for the app. |
| worker_extraction.autoscaling.maxReplicas | int | `3` | Maximum number of replicas for the app. |
| worker_extraction.autoscaling.minReplicas | int | `1` | Minimum number of replicas for the app. |
| worker_extraction.autoscaling.targetCPUUtilizationPercentage | int | `80` | Average CPU utilization percentage for the app. |
| worker_extraction.autoscaling.targetMemoryUtilizationPercentage | int | `80` | Average memory utilization percentage for the app. |

#### GrpcRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_extraction.grpcRoute.annotations | object | `{}` | Additional GRPCRoute annotations. |
| worker_extraction.grpcRoute.enabled | bool | `false` | Enable a GRPCRoute resource for this service. |
| worker_extraction.grpcRoute.hostnames | list | `[]` | Hostnames for the GRPCRoute to match. |
| worker_extraction.grpcRoute.labels | object | `{}` | Additional GRPCRoute labels. |
| worker_extraction.grpcRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the GRPCRoute to. |
| worker_extraction.grpcRoute.rules | list | `[]` | Routing rules for the GRPCRoute. |

#### HttpRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_extraction.httpRoute.annotations | object | `{}` | Additional HTTPRoute annotations. |
| worker_extraction.httpRoute.enabled | bool | `false` | Enable an HTTPRoute resource for this service. |
| worker_extraction.httpRoute.hostnames | list | `[]` | Hostnames for the HTTPRoute to match. |
| worker_extraction.httpRoute.labels | object | `{}` | Additional HTTPRoute labels. |
| worker_extraction.httpRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the HTTPRoute to. |
| worker_extraction.httpRoute.rules | list | `[]` | Routing rules for the HTTPRoute. |

#### Image

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_extraction.image.digest | string | `""` | Image digest (`sha256:...`). When set it takes precedence over `tag`, pinning the exact image content so the same release can never resolve to a different build - preferred over a mutable tag for anything you deploy to production. |
| worker_extraction.image.pullPolicy | string | `"IfNotPresent"` | Image pull policy for the app. |
| worker_extraction.image.registry | string | `"ghcr.io"` | Registry to use for the app. |
| worker_extraction.image.repository | string | `"ia-generative/mille-feuille/worker-extraction"` | Repository to use for the app. |
| worker_extraction.image.tag | string | `""` | Tag to use for the app. Overrides the image tag whose default is the chart appVersion. |

#### Ingress

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_extraction.ingress.annotations | object | `{}` | Additional ingress annotations. |
| worker_extraction.ingress.className | string | `""` | Defines which ingress controller will implement the resource. |
| worker_extraction.ingress.enabled | bool | `false` | Whether or not ingress should be enabled. |
| worker_extraction.ingress.hosts[0].name | string | `"domain.local"` | Name of the host record. |
| worker_extraction.ingress.hosts[0].paths | list | `[{"backend":{"portNumber":null,"serviceName":""},"path":"/","pathType":"Prefix"}]` | Paths of the host record to manage routing (avoids repeating the same host for multiple paths/backends). |
| worker_extraction.ingress.hosts[0].paths[0].backend.portNumber | string | `nil` | Port used by the backend service linked to the path (leave null to use the app service port). |
| worker_extraction.ingress.hosts[0].paths[0].backend.serviceName | string | `""` | Name of the backend service linked to the path (leave empty to use the app service). |
| worker_extraction.ingress.hosts[0].paths[0].path | string | `"/"` | Path of the host record to manage routing. |
| worker_extraction.ingress.hosts[0].paths[0].pathType | string | `"Prefix"` | Path type of the host record. |
| worker_extraction.ingress.labels | object | `{}` | Additional ingress labels. |
| worker_extraction.ingress.tls | list | `[]` | Enable TLS configuration. |

#### Metrics

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_extraction.metrics.enabled | bool | `false` | Deploy metrics service. |
| worker_extraction.metrics.service.annotations | object | `{}` | Metrics service annotations. |
| worker_extraction.metrics.service.labels | object | `{}` | Metrics service labels. |
| worker_extraction.metrics.service.port | int | `9000` | Metrics service port. |
| worker_extraction.metrics.service.portName | string | `"metrics"` | Metrics service port name. |
| worker_extraction.metrics.service.targetPort | int | `9000` | Metrics service target port. |
| worker_extraction.metrics.service.type | string | `"ClusterIP"` | Type of metrics service to create. |
| worker_extraction.metrics.serviceMonitor.annotations | object | `{}` | Prometheus ServiceMonitor annotations. |
| worker_extraction.metrics.serviceMonitor.enabled | bool | `false` | Enable a prometheus ServiceMonitor. |
| worker_extraction.metrics.serviceMonitor.endpoints[0].basicAuth.password | string | `""` | The secret in the service monitor namespace that contains the password for authentication. |
| worker_extraction.metrics.serviceMonitor.endpoints[0].basicAuth.username | string | `""` | The secret in the service monitor namespace that contains the username for authentication. |
| worker_extraction.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.key | string | `""` | Secret key to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| worker_extraction.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.name | string | `""` | Secret name to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| worker_extraction.metrics.serviceMonitor.endpoints[0].honorLabels | bool | `false` | When true, honorLabels preserves the metric’s labels when they collide with the target’s labels. |
| worker_extraction.metrics.serviceMonitor.endpoints[0].interval | string | `"30s"` | Prometheus ServiceMonitor interval. |
| worker_extraction.metrics.serviceMonitor.endpoints[0].metricRelabelings | list | `[]` | Prometheus MetricRelabelConfigs to apply to samples before ingestion. |
| worker_extraction.metrics.serviceMonitor.endpoints[0].path | string | `"/metrics"` | Path used by the Prometheus ServiceMonitor to scrape metrics. |
| worker_extraction.metrics.serviceMonitor.endpoints[0].relabelings | list | `[]` | Prometheus RelabelConfigs to apply to samples before scraping. |
| worker_extraction.metrics.serviceMonitor.endpoints[0].scheme | string | `""` | Prometheus ServiceMonitor scheme. |
| worker_extraction.metrics.serviceMonitor.endpoints[0].scrapeTimeout | string | `"10s"` | Prometheus ServiceMonitor scrapeTimeout. If empty, Prometheus uses the global scrape timeout unless it is less than the target's scrape interval value in which the latter is used. |
| worker_extraction.metrics.serviceMonitor.endpoints[0].selector | object | `{}` | Prometheus ServiceMonitor selector. |
| worker_extraction.metrics.serviceMonitor.endpoints[0].tlsConfig | object | `{}` | Prometheus ServiceMonitor tlsConfig. |
| worker_extraction.metrics.serviceMonitor.labels | object | `{}` | Prometheus ServiceMonitor labels. |

#### NetworkPolicy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_extraction.networkPolicy.annotations | object | `{}` | Annotations to be added to the app NetworkPolicy. |
| worker_extraction.networkPolicy.create | bool | `false` | Create NetworkPolicy object for the app. The policy always selects this component's pods only (via its selector labels), never the whole namespace. |
| worker_extraction.networkPolicy.egress | list | `[]` | Egress rules for the NetworkPolicy object. |
| worker_extraction.networkPolicy.ingress | list | `[]` | Ingress rules for the NetworkPolicy object. |
| worker_extraction.networkPolicy.labels | object | `{}` | Labels to be added to the app NetworkPolicy. |
| worker_extraction.networkPolicy.policyTypes | list | `["Ingress"]` | Policy types used in the NetworkPolicy object. |

#### Pdb

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_extraction.pdb.annotations | object | `{}` | Annotations to be added to app pdb. |
| worker_extraction.pdb.enabled | bool | `false` | Deploy a PodDisruptionBudget for the app |
| worker_extraction.pdb.labels | object | `{}` | Labels to be added to app pdb. |
| worker_extraction.pdb.maxUnavailable | string | `""` | Number of pods that are unavailable after eviction as number or percentage (eg.: 50%). Has higher precedence over `worker_extraction.pdb.minAvailable`. |
| worker_extraction.pdb.minAvailable | string | `""` | Number of pods that are available after eviction as number or percentage (eg.: 50%). One of `minAvailable` / `maxUnavailable` must be set when `pdb.enabled` is true - a budget of 0 is the same as having no budget at all, so leaving both empty fails at render time. |

#### Probes

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_extraction.probes.livenessProbe.failureThreshold | int | `3` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_extraction.probes.livenessProbe.httpGet.path | string | `"/"` | Worker_extraction container healthcheck endpoint (livenessProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_extraction.probes.livenessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_extraction.probes.livenessProbe.initialDelaySeconds | int | `30` | Number of seconds after the container has started before probe is initiated. |
| worker_extraction.probes.livenessProbe.periodSeconds | int | `30` | How often (in seconds) to perform the probe. |
| worker_extraction.probes.livenessProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_extraction.probes.livenessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| worker_extraction.probes.readinessProbe.failureThreshold | int | `2` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_extraction.probes.readinessProbe.httpGet.path | string | `"/"` | Worker_extraction container healthcheck endpoint (readinessProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_extraction.probes.readinessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_extraction.probes.readinessProbe.initialDelaySeconds | int | `10` | Number of seconds after the container has started before probe is initiated. |
| worker_extraction.probes.readinessProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| worker_extraction.probes.readinessProbe.successThreshold | int | `2` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_extraction.probes.readinessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| worker_extraction.probes.startupProbe.failureThreshold | int | `10` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_extraction.probes.startupProbe.httpGet.path | string | `"/"` | Worker_extraction container healthcheck endpoint (startupProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_extraction.probes.startupProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_extraction.probes.startupProbe.initialDelaySeconds | int | `0` | Number of seconds after the container has started before probe is initiated. |
| worker_extraction.probes.startupProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| worker_extraction.probes.startupProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_extraction.probes.startupProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |

#### Resources

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_extraction.resources.limits.cpu | string | `"500m"` | CPU limit for the app. |
| worker_extraction.resources.limits.memory | string | `"2Gi"` | Memory limit for the app. |
| worker_extraction.resources.requests.cpu | string | `"100m"` | CPU request for the app. |
| worker_extraction.resources.requests.memory | string | `"256Mi"` | Memory request for the app. |

#### Service

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_extraction.service.enabled | bool | `true` | Whether or not to create a Service for the app. Set to `false` for components that don't accept traffic (e.g. a queue consumer with no `containerPort`). |
| worker_extraction.service.extraPorts | list | `[]` | Extra service ports. |
| worker_extraction.service.nodePort | int | `null` (allocated by Kubernetes) | Port used when type is `NodePort` to expose the service on the given node port. Left empty, Kubernetes allocates one from the configured node-port range, which avoids two releases of this chart colliding on the same hardcoded port. |
| worker_extraction.service.port | int | `80` | Port used by the service. |
| worker_extraction.service.portName | string | `"http"` | Port name used by the service. |
| worker_extraction.service.protocol | string | `"TCP"` | Protocol used by the service. |
| worker_extraction.service.type | string | `"ClusterIP"` | Type of service to create for the app. |

#### ServiceAccount

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_extraction.serviceAccount.annotations | object | `{}` | Annotations applied to created service account. |
| worker_extraction.serviceAccount.automountServiceAccountToken | bool | `false` | Should the service account access token be automount in the pod. |
| worker_extraction.serviceAccount.clusterRole.create | bool | `false` | Should the clusterRole be created. |
| worker_extraction.serviceAccount.clusterRole.rules | list | `[]` | ClusterRole rules associated with the service account. |
| worker_extraction.serviceAccount.create | bool | `false` | Create a service account. |
| worker_extraction.serviceAccount.enabled | bool | `false` | Enable the service account. |
| worker_extraction.serviceAccount.name | string | `""` | Service account name. |
| worker_extraction.serviceAccount.role.create | bool | `false` | Should the role be created. |
| worker_extraction.serviceAccount.role.rules | list | `[]` | Role rules associated with the service account. |

#### Strategy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_extraction.strategy.rollingUpdate.maxSurge | int | `1` | The maximum number of pods that can be scheduled above the desired number of pods. |
| worker_extraction.strategy.rollingUpdate.maxUnavailable | int | `1` | The maximum number of pods that can be unavailable during the update process. |
| worker_extraction.strategy.type | string | `"RollingUpdate"` | Strategy type used to replace old Pods by new ones, can be `Recreate` or `RollingUpdate`. Only applied when `deploymentType` is "Deployment". |

### WorkerOcr

#### General

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr.affinity | object | `{}` | Affinity used for app pod. |
| worker_ocr.args | list | `[]` | Worker_ocr container command args. |
| worker_ocr.automountServiceAccountToken | bool | `false` | Mount the ServiceAccount token into the app pods. Defaults to false so a compromised container holds no API credentials; the API server does not need the token unless the app actually talks to the Kubernetes API. Applied at pod level so it holds even when `serviceAccount.name` points at an SA that automounts. |
| worker_ocr.command | list | `[]` | Worker_ocr container command. |
| worker_ocr.containerPort | int | `8080` | Worker_ocr container port number. Set to `null`/`0` (and disable `service`/probes) for components that don't listen on any port (e.g. a queue consumer). |
| worker_ocr.containerPortName | string | `"http"` | Worker_ocr container port name. |
| worker_ocr.deploymentType | string | `"Deployment"` | Workload kind to deploy the app as. One of "Deployment", "StatefulSet" or "DaemonSet" (validated at render time - an unknown value fails instead of producing a release with no workload). Use the top-level `jobs` / `cronjobs` maps for one-off or scheduled workloads. Some values only apply to certain kinds: `replicaCount`/`autoscaling` and `strategy` are Deployment-only (`autoscaling` also works on a StatefulSet), `volumeClaims`/`extraVolumeClaims` are StatefulSet-only, and `updateStrategy` covers StatefulSet and DaemonSet. |
| worker_ocr.dnsConfig | object | `{}` | Pod DNS configuration, merged with `dnsPolicy` by the kubelet. |
| worker_ocr.dnsPolicy | string | `""` (`ClusterFirstWithHostNet` when `hostNetwork` is true) | Pod DNS policy. Left empty, it defaults to `ClusterFirstWithHostNet` when `hostNetwork` is true (otherwise a hostNetwork pod silently stops resolving cluster DNS) and to the Kubernetes default `ClusterFirst` when it isn't. |
| worker_ocr.enableServiceLinks | bool | `false` | Inject the legacy `{SVC}_SERVICE_HOST`/`_PORT` environment variables for every Service in the namespace. Defaults to false: the variables are rarely used, leak the namespace's topology into every container, and can collide with the app's own configuration. Set to true only for an app that genuinely reads them. |
| worker_ocr.enabled | bool | `false` | Déploie le pod d'OCR « texte des régions des pages scannées (PP-OCRv5) » (OCR_ENGINE=layout de `worker_document`). Désactivé par défaut : il porte un modèle ONNX et n'a de sens qu'avec les autres pods d'OCR. Voir worker/document_process/README.md. |
| worker_ocr.env | object | `{}` | Map or array of environment variables to inject into the app container (`valueFrom` supported). |
| worker_ocr.envCm | object | `{}` | Map of environment variables to inject into a configmap loaded by the app container (`valueFrom` not supported). |
| worker_ocr.envFrom | list | `[]` | Worker_ocr container env variables loaded from configmap or secret reference. List or map (merged with `global.envFrom` above, global entries first); see `global.envFrom` for both forms. |
| worker_ocr.envSecret | object | `{}` | Map of environment variables to inject into a secret loaded by the app container (`valueFrom` not supported). Values placed here are stored in plain text in the values file AND in the Helm release secret, so use it for non-sensitive-but-secret-shaped config only. For real credentials prefer referencing a Secret you manage elsewhere via `envFrom`, or have an operator materialise it (see the `VaultStaticSecret` example under `extraObjects`). |
| worker_ocr.extraContainers | list | `[]` | Extra containers to add to the app pod as sidecars. |
| worker_ocr.extraPorts | list | `[]` | Worker_ocr extra container ports. |
| worker_ocr.extraVolumeClaims | list | `[]` | Additional volumeClaims to add, concatenated with `volumeClaims` above at render time. |
| worker_ocr.extraVolumeMounts | list | `[]` | Additional volumeMounts to add, concatenated with `volumeMounts` above at render time. |
| worker_ocr.extraVolumes | list | `[]` | Additional volumes to add, concatenated with `volumes` above at render time (e.g. to mount a cert or config from a values override without repeating the chart's own volumes). |
| worker_ocr.hostAliases | list | `[]` | Host aliases that will be injected at pod-level into /etc/hosts. |
| worker_ocr.hostNetwork | bool | `false` | Share the host network namespace. Container ports then bind directly on the node, so they must not collide with anything else running there. |
| worker_ocr.hostPID | bool | `false` | Share the host PID namespace (lets the container see and signal host processes). |
| worker_ocr.imagePullSecrets | list | `[]` | Image credentials configuration. |
| worker_ocr.initContainers | list | `[]` | Init containers to add to the app pod. |
| worker_ocr.nodeSelector | object | `{}` | Default node selector for app. |
| worker_ocr.podAnnotations | object | `{}` | Annotations for the app deployed pods. |
| worker_ocr.podLabels | object | `{}` | Labels for the app deployed pods. |
| worker_ocr.podSecurityContext | object | `{"fsGroup":1000,"fsGroupChangePolicy":"OnRootMismatch","runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000,"seccompProfile":{"type":"RuntimeDefault"}}` | Pod-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard. Rendered via `toYaml`, so any `PodSecurityContext` field is accepted. Adjust the UID/GID to whatever your image actually ships with - `runAsNonRoot` makes the kubelet refuse to start a container that would run as root, which is the intended failure mode rather than something to switch off. Set to `null` to omit the block entirely. |
| worker_ocr.priorityClassName | string | `""` | PriorityClass to schedule the pods with (e.g. `system-node-critical` for a node agent that must not be evicted under pressure). |
| worker_ocr.replicaCount | int | `1` | The number of application controller pods to run. Ignored when `deploymentType` is "DaemonSet" (one pod per node) or when `autoscaling.enabled` is true. |
| worker_ocr.revisionHistoryLimit | int | `10` | Revision history limit for the app. |
| worker_ocr.securityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"privileged":false,"readOnlyRootFilesystem":true,"runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000}` | Container-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard: no privilege escalation, no capabilities, immutable root filesystem. Rendered via `toYaml`, so any `SecurityContext` field is accepted. Note `readOnlyRootFilesystem` requires the app to write only to mounted volumes - the default `volumes`/`volumeMounts` below provide an `emptyDir` on /tmp for that reason. Set to `null` to omit the block entirely. |
| worker_ocr.terminationGracePeriodSeconds | int | `null` (Kubernetes default of 30) | Grace period, in seconds, given to the pod to shut down cleanly before it is killed. |
| worker_ocr.tolerations | list | `[]` | Default tolerations for app. |
| worker_ocr.topologySpreadConstraints | list | `[]` | Topology spread constraints used to spread the pods across failure domains. |
| worker_ocr.updateStrategy | object | `{}` | Update strategy applied when `deploymentType` is "StatefulSet" or "DaemonSet" (ignored for a Deployment, which uses `strategy` above). Rendered verbatim via `toYaml`, so it takes the native `StatefulSetUpdateStrategy`/`DaemonSetUpdateStrategy` shape of the selected kind; left empty, Kubernetes applies its own default (`RollingUpdate` for both). |
| worker_ocr.volumeClaims | list | `[]` | List of volumeClaims to add, rendered as the StatefulSet's `volumeClaimTemplates`. Requires `deploymentType: "StatefulSet"` - setting it on a Deployment or DaemonSet fails at render time rather than being silently dropped (use `volumes`/`extraVolumes` there instead). |
| worker_ocr.volumeMounts | list | `[{"mountPath":"/tmp","name":"tmp"}]` | List of mounts to add (normally used with `volumes` or `volumeClaims`). Prefer this for mounts the chart itself always needs; use `extraVolumeMounts` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to the `/tmp` mount backing the hardened `readOnlyRootFilesystem` default (see `volumes` above). |
| worker_ocr.volumes | list | `[{"emptyDir":{},"name":"tmp"}]` | List of volumes to add. Prefer this for volumes the chart itself always needs (e.g. security-hardening `emptyDir`s); use `extraVolumes` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to a `/tmp` `emptyDir`, which is what makes the default `securityContext.readOnlyRootFilesystem: true` usable - drop it only if you also relax that. Helm replaces lists wholesale rather than merging them, so overriding this key means restating the entries you want to keep. |

#### Autoscaling

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr.autoscaling.enabled | bool | `false` | Enable Horizontal Pod Autoscaler for the app. |
| worker_ocr.autoscaling.maxReplicas | int | `3` | Maximum number of replicas for the app. |
| worker_ocr.autoscaling.minReplicas | int | `1` | Minimum number of replicas for the app. |
| worker_ocr.autoscaling.targetCPUUtilizationPercentage | int | `80` | Average CPU utilization percentage for the app. |
| worker_ocr.autoscaling.targetMemoryUtilizationPercentage | int | `80` | Average memory utilization percentage for the app. |

#### GrpcRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr.grpcRoute.annotations | object | `{}` | Additional GRPCRoute annotations. |
| worker_ocr.grpcRoute.enabled | bool | `false` | Enable a GRPCRoute resource for this service. |
| worker_ocr.grpcRoute.hostnames | list | `[]` | Hostnames for the GRPCRoute to match. |
| worker_ocr.grpcRoute.labels | object | `{}` | Additional GRPCRoute labels. |
| worker_ocr.grpcRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the GRPCRoute to. |
| worker_ocr.grpcRoute.rules | list | `[]` | Routing rules for the GRPCRoute. |

#### HttpRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr.httpRoute.annotations | object | `{}` | Additional HTTPRoute annotations. |
| worker_ocr.httpRoute.enabled | bool | `false` | Enable an HTTPRoute resource for this service. |
| worker_ocr.httpRoute.hostnames | list | `[]` | Hostnames for the HTTPRoute to match. |
| worker_ocr.httpRoute.labels | object | `{}` | Additional HTTPRoute labels. |
| worker_ocr.httpRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the HTTPRoute to. |
| worker_ocr.httpRoute.rules | list | `[]` | Routing rules for the HTTPRoute. |

#### Image

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr.image.digest | string | `""` | Image digest (`sha256:...`). When set it takes precedence over `tag`, pinning the exact image content so the same release can never resolve to a different build - preferred over a mutable tag for anything you deploy to production. |
| worker_ocr.image.pullPolicy | string | `"IfNotPresent"` | Image pull policy for the app. |
| worker_ocr.image.registry | string | `"ghcr.io"` | Registry to use for the app. |
| worker_ocr.image.repository | string | `"ia-generative/mille-feuille/worker-ocr"` | Repository to use for the app. |
| worker_ocr.image.tag | string | `""` | Tag to use for the app. Overrides the image tag whose default is the chart appVersion. |

#### Ingress

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr.ingress.annotations | object | `{}` | Additional ingress annotations. |
| worker_ocr.ingress.className | string | `""` | Defines which ingress controller will implement the resource. |
| worker_ocr.ingress.enabled | bool | `false` | Whether or not ingress should be enabled. |
| worker_ocr.ingress.hosts[0].name | string | `"domain.local"` | Name of the host record. |
| worker_ocr.ingress.hosts[0].paths | list | `[{"backend":{"portNumber":null,"serviceName":""},"path":"/","pathType":"Prefix"}]` | Paths of the host record to manage routing (avoids repeating the same host for multiple paths/backends). |
| worker_ocr.ingress.hosts[0].paths[0].backend.portNumber | string | `nil` | Port used by the backend service linked to the path (leave null to use the app service port). |
| worker_ocr.ingress.hosts[0].paths[0].backend.serviceName | string | `""` | Name of the backend service linked to the path (leave empty to use the app service). |
| worker_ocr.ingress.hosts[0].paths[0].path | string | `"/"` | Path of the host record to manage routing. |
| worker_ocr.ingress.hosts[0].paths[0].pathType | string | `"Prefix"` | Path type of the host record. |
| worker_ocr.ingress.labels | object | `{}` | Additional ingress labels. |
| worker_ocr.ingress.tls | list | `[]` | Enable TLS configuration. |

#### Metrics

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr.metrics.enabled | bool | `false` | Deploy metrics service. |
| worker_ocr.metrics.service.annotations | object | `{}` | Metrics service annotations. |
| worker_ocr.metrics.service.labels | object | `{}` | Metrics service labels. |
| worker_ocr.metrics.service.port | int | `9000` | Metrics service port. |
| worker_ocr.metrics.service.portName | string | `"metrics"` | Metrics service port name. |
| worker_ocr.metrics.service.targetPort | int | `9000` | Metrics service target port. |
| worker_ocr.metrics.service.type | string | `"ClusterIP"` | Type of metrics service to create. |
| worker_ocr.metrics.serviceMonitor.annotations | object | `{}` | Prometheus ServiceMonitor annotations. |
| worker_ocr.metrics.serviceMonitor.enabled | bool | `false` | Enable a prometheus ServiceMonitor. |
| worker_ocr.metrics.serviceMonitor.endpoints[0].basicAuth.password | string | `""` | The secret in the service monitor namespace that contains the password for authentication. |
| worker_ocr.metrics.serviceMonitor.endpoints[0].basicAuth.username | string | `""` | The secret in the service monitor namespace that contains the username for authentication. |
| worker_ocr.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.key | string | `""` | Secret key to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| worker_ocr.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.name | string | `""` | Secret name to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| worker_ocr.metrics.serviceMonitor.endpoints[0].honorLabels | bool | `false` | When true, honorLabels preserves the metric’s labels when they collide with the target’s labels. |
| worker_ocr.metrics.serviceMonitor.endpoints[0].interval | string | `"30s"` | Prometheus ServiceMonitor interval. |
| worker_ocr.metrics.serviceMonitor.endpoints[0].metricRelabelings | list | `[]` | Prometheus MetricRelabelConfigs to apply to samples before ingestion. |
| worker_ocr.metrics.serviceMonitor.endpoints[0].path | string | `"/metrics"` | Path used by the Prometheus ServiceMonitor to scrape metrics. |
| worker_ocr.metrics.serviceMonitor.endpoints[0].relabelings | list | `[]` | Prometheus RelabelConfigs to apply to samples before scraping. |
| worker_ocr.metrics.serviceMonitor.endpoints[0].scheme | string | `""` | Prometheus ServiceMonitor scheme. |
| worker_ocr.metrics.serviceMonitor.endpoints[0].scrapeTimeout | string | `"10s"` | Prometheus ServiceMonitor scrapeTimeout. If empty, Prometheus uses the global scrape timeout unless it is less than the target's scrape interval value in which the latter is used. |
| worker_ocr.metrics.serviceMonitor.endpoints[0].selector | object | `{}` | Prometheus ServiceMonitor selector. |
| worker_ocr.metrics.serviceMonitor.endpoints[0].tlsConfig | object | `{}` | Prometheus ServiceMonitor tlsConfig. |
| worker_ocr.metrics.serviceMonitor.labels | object | `{}` | Prometheus ServiceMonitor labels. |

#### NetworkPolicy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr.networkPolicy.annotations | object | `{}` | Annotations to be added to the app NetworkPolicy. |
| worker_ocr.networkPolicy.create | bool | `false` | Create NetworkPolicy object for the app. The policy always selects this component's pods only (via its selector labels), never the whole namespace. |
| worker_ocr.networkPolicy.egress | list | `[]` | Egress rules for the NetworkPolicy object. |
| worker_ocr.networkPolicy.ingress | list | `[]` | Ingress rules for the NetworkPolicy object. |
| worker_ocr.networkPolicy.labels | object | `{}` | Labels to be added to the app NetworkPolicy. |
| worker_ocr.networkPolicy.policyTypes | list | `["Ingress"]` | Policy types used in the NetworkPolicy object. |

#### Pdb

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr.pdb.annotations | object | `{}` | Annotations to be added to app pdb. |
| worker_ocr.pdb.enabled | bool | `false` | Deploy a PodDisruptionBudget for the app |
| worker_ocr.pdb.labels | object | `{}` | Labels to be added to app pdb. |
| worker_ocr.pdb.maxUnavailable | string | `""` | Number of pods that are unavailable after eviction as number or percentage (eg.: 50%). Has higher precedence over `worker_ocr.pdb.minAvailable`. |
| worker_ocr.pdb.minAvailable | string | `""` | Number of pods that are available after eviction as number or percentage (eg.: 50%). One of `minAvailable` / `maxUnavailable` must be set when `pdb.enabled` is true - a budget of 0 is the same as having no budget at all, so leaving both empty fails at render time. |

#### Probes

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr.probes.livenessProbe.failureThreshold | int | `3` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_ocr.probes.livenessProbe.httpGet.path | string | `"/"` | Worker_ocr container healthcheck endpoint (livenessProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_ocr.probes.livenessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_ocr.probes.livenessProbe.initialDelaySeconds | int | `30` | Number of seconds after the container has started before probe is initiated. |
| worker_ocr.probes.livenessProbe.periodSeconds | int | `30` | How often (in seconds) to perform the probe. |
| worker_ocr.probes.livenessProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_ocr.probes.livenessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| worker_ocr.probes.readinessProbe.failureThreshold | int | `2` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_ocr.probes.readinessProbe.httpGet.path | string | `"/"` | Worker_ocr container healthcheck endpoint (readinessProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_ocr.probes.readinessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_ocr.probes.readinessProbe.initialDelaySeconds | int | `10` | Number of seconds after the container has started before probe is initiated. |
| worker_ocr.probes.readinessProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| worker_ocr.probes.readinessProbe.successThreshold | int | `2` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_ocr.probes.readinessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| worker_ocr.probes.startupProbe.failureThreshold | int | `10` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_ocr.probes.startupProbe.httpGet.path | string | `"/"` | Worker_ocr container healthcheck endpoint (startupProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_ocr.probes.startupProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_ocr.probes.startupProbe.initialDelaySeconds | int | `0` | Number of seconds after the container has started before probe is initiated. |
| worker_ocr.probes.startupProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| worker_ocr.probes.startupProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_ocr.probes.startupProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |

#### Resources

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr.resources.limits.cpu | string | `"500m"` | CPU limit for the app. |
| worker_ocr.resources.limits.memory | string | `"2Gi"` | Memory limit for the app. |
| worker_ocr.resources.requests.cpu | string | `"100m"` | CPU request for the app. |
| worker_ocr.resources.requests.memory | string | `"256Mi"` | Memory request for the app. |

#### Service

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr.service.enabled | bool | `true` | Whether or not to create a Service for the app. Set to `false` for components that don't accept traffic (e.g. a queue consumer with no `containerPort`). |
| worker_ocr.service.extraPorts | list | `[]` | Extra service ports. |
| worker_ocr.service.nodePort | int | `null` (allocated by Kubernetes) | Port used when type is `NodePort` to expose the service on the given node port. Left empty, Kubernetes allocates one from the configured node-port range, which avoids two releases of this chart colliding on the same hardcoded port. |
| worker_ocr.service.port | int | `80` | Port used by the service. |
| worker_ocr.service.portName | string | `"http"` | Port name used by the service. |
| worker_ocr.service.protocol | string | `"TCP"` | Protocol used by the service. |
| worker_ocr.service.type | string | `"ClusterIP"` | Type of service to create for the app. |

#### ServiceAccount

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr.serviceAccount.annotations | object | `{}` | Annotations applied to created service account. |
| worker_ocr.serviceAccount.automountServiceAccountToken | bool | `false` | Should the service account access token be automount in the pod. |
| worker_ocr.serviceAccount.clusterRole.create | bool | `false` | Should the clusterRole be created. |
| worker_ocr.serviceAccount.clusterRole.rules | list | `[]` | ClusterRole rules associated with the service account. |
| worker_ocr.serviceAccount.create | bool | `false` | Create a service account. |
| worker_ocr.serviceAccount.enabled | bool | `false` | Enable the service account. |
| worker_ocr.serviceAccount.name | string | `""` | Service account name. |
| worker_ocr.serviceAccount.role.create | bool | `false` | Should the role be created. |
| worker_ocr.serviceAccount.role.rules | list | `[]` | Role rules associated with the service account. |

#### Strategy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr.strategy.rollingUpdate.maxSurge | int | `1` | The maximum number of pods that can be scheduled above the desired number of pods. |
| worker_ocr.strategy.rollingUpdate.maxUnavailable | int | `1` | The maximum number of pods that can be unavailable during the update process. |
| worker_ocr.strategy.type | string | `"RollingUpdate"` | Strategy type used to replace old Pods by new ones, can be `Recreate` or `RollingUpdate`. Only applied when `deploymentType` is "Deployment". |

### WorkerOcrLayout

#### General

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_layout.affinity | object | `{}` | Affinity used for app pod. |
| worker_ocr_layout.args | list | `[]` | Worker_ocr_layout container command args. |
| worker_ocr_layout.automountServiceAccountToken | bool | `false` | Mount the ServiceAccount token into the app pods. Defaults to false so a compromised container holds no API credentials; the API server does not need the token unless the app actually talks to the Kubernetes API. Applied at pod level so it holds even when `serviceAccount.name` points at an SA that automounts. |
| worker_ocr_layout.command | list | `[]` | Worker_ocr_layout container command. |
| worker_ocr_layout.containerPort | int | `8080` | Worker_ocr_layout container port number. Set to `null`/`0` (and disable `service`/probes) for components that don't listen on any port (e.g. a queue consumer). |
| worker_ocr_layout.containerPortName | string | `"http"` | Worker_ocr_layout container port name. |
| worker_ocr_layout.deploymentType | string | `"Deployment"` | Workload kind to deploy the app as. One of "Deployment", "StatefulSet" or "DaemonSet" (validated at render time - an unknown value fails instead of producing a release with no workload). Use the top-level `jobs` / `cronjobs` maps for one-off or scheduled workloads. Some values only apply to certain kinds: `replicaCount`/`autoscaling` and `strategy` are Deployment-only (`autoscaling` also works on a StatefulSet), `volumeClaims`/`extraVolumeClaims` are StatefulSet-only, and `updateStrategy` covers StatefulSet and DaemonSet. |
| worker_ocr_layout.dnsConfig | object | `{}` | Pod DNS configuration, merged with `dnsPolicy` by the kubelet. |
| worker_ocr_layout.dnsPolicy | string | `""` (`ClusterFirstWithHostNet` when `hostNetwork` is true) | Pod DNS policy. Left empty, it defaults to `ClusterFirstWithHostNet` when `hostNetwork` is true (otherwise a hostNetwork pod silently stops resolving cluster DNS) and to the Kubernetes default `ClusterFirst` when it isn't. |
| worker_ocr_layout.enableServiceLinks | bool | `false` | Inject the legacy `{SVC}_SERVICE_HOST`/`_PORT` environment variables for every Service in the namespace. Defaults to false: the variables are rarely used, leak the namespace's topology into every container, and can collide with the app's own configuration. Set to true only for an app that genuinely reads them. |
| worker_ocr_layout.enabled | bool | `false` | Déploie le pod d'OCR « layout des pages scannées (PP-DocLayoutV3) » (OCR_ENGINE=layout de `worker_document`). Désactivé par défaut : il porte un modèle ONNX et n'a de sens qu'avec les autres pods d'OCR. Voir worker/document_process/README.md. |
| worker_ocr_layout.env | object | `{}` | Map or array of environment variables to inject into the app container (`valueFrom` supported). |
| worker_ocr_layout.envCm | object | `{}` | Map of environment variables to inject into a configmap loaded by the app container (`valueFrom` not supported). |
| worker_ocr_layout.envFrom | list | `[]` | Worker_ocr_layout container env variables loaded from configmap or secret reference. List or map (merged with `global.envFrom` above, global entries first); see `global.envFrom` for both forms. |
| worker_ocr_layout.envSecret | object | `{}` | Map of environment variables to inject into a secret loaded by the app container (`valueFrom` not supported). Values placed here are stored in plain text in the values file AND in the Helm release secret, so use it for non-sensitive-but-secret-shaped config only. For real credentials prefer referencing a Secret you manage elsewhere via `envFrom`, or have an operator materialise it (see the `VaultStaticSecret` example under `extraObjects`). |
| worker_ocr_layout.extraContainers | list | `[]` | Extra containers to add to the app pod as sidecars. |
| worker_ocr_layout.extraPorts | list | `[]` | Worker_ocr_layout extra container ports. |
| worker_ocr_layout.extraVolumeClaims | list | `[]` | Additional volumeClaims to add, concatenated with `volumeClaims` above at render time. |
| worker_ocr_layout.extraVolumeMounts | list | `[]` | Additional volumeMounts to add, concatenated with `volumeMounts` above at render time. |
| worker_ocr_layout.extraVolumes | list | `[]` | Additional volumes to add, concatenated with `volumes` above at render time (e.g. to mount a cert or config from a values override without repeating the chart's own volumes). |
| worker_ocr_layout.hostAliases | list | `[]` | Host aliases that will be injected at pod-level into /etc/hosts. |
| worker_ocr_layout.hostNetwork | bool | `false` | Share the host network namespace. Container ports then bind directly on the node, so they must not collide with anything else running there. |
| worker_ocr_layout.hostPID | bool | `false` | Share the host PID namespace (lets the container see and signal host processes). |
| worker_ocr_layout.imagePullSecrets | list | `[]` | Image credentials configuration. |
| worker_ocr_layout.initContainers | list | `[]` | Init containers to add to the app pod. |
| worker_ocr_layout.nodeSelector | object | `{}` | Default node selector for app. |
| worker_ocr_layout.podAnnotations | object | `{}` | Annotations for the app deployed pods. |
| worker_ocr_layout.podLabels | object | `{}` | Labels for the app deployed pods. |
| worker_ocr_layout.podSecurityContext | object | `{"fsGroup":1000,"fsGroupChangePolicy":"OnRootMismatch","runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000,"seccompProfile":{"type":"RuntimeDefault"}}` | Pod-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard. Rendered via `toYaml`, so any `PodSecurityContext` field is accepted. Adjust the UID/GID to whatever your image actually ships with - `runAsNonRoot` makes the kubelet refuse to start a container that would run as root, which is the intended failure mode rather than something to switch off. Set to `null` to omit the block entirely. |
| worker_ocr_layout.priorityClassName | string | `""` | PriorityClass to schedule the pods with (e.g. `system-node-critical` for a node agent that must not be evicted under pressure). |
| worker_ocr_layout.replicaCount | int | `1` | The number of application controller pods to run. Ignored when `deploymentType` is "DaemonSet" (one pod per node) or when `autoscaling.enabled` is true. |
| worker_ocr_layout.revisionHistoryLimit | int | `10` | Revision history limit for the app. |
| worker_ocr_layout.securityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"privileged":false,"readOnlyRootFilesystem":true,"runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000}` | Container-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard: no privilege escalation, no capabilities, immutable root filesystem. Rendered via `toYaml`, so any `SecurityContext` field is accepted. Note `readOnlyRootFilesystem` requires the app to write only to mounted volumes - the default `volumes`/`volumeMounts` below provide an `emptyDir` on /tmp for that reason. Set to `null` to omit the block entirely. |
| worker_ocr_layout.terminationGracePeriodSeconds | int | `null` (Kubernetes default of 30) | Grace period, in seconds, given to the pod to shut down cleanly before it is killed. |
| worker_ocr_layout.tolerations | list | `[]` | Default tolerations for app. |
| worker_ocr_layout.topologySpreadConstraints | list | `[]` | Topology spread constraints used to spread the pods across failure domains. |
| worker_ocr_layout.updateStrategy | object | `{}` | Update strategy applied when `deploymentType` is "StatefulSet" or "DaemonSet" (ignored for a Deployment, which uses `strategy` above). Rendered verbatim via `toYaml`, so it takes the native `StatefulSetUpdateStrategy`/`DaemonSetUpdateStrategy` shape of the selected kind; left empty, Kubernetes applies its own default (`RollingUpdate` for both). |
| worker_ocr_layout.volumeClaims | list | `[]` | List of volumeClaims to add, rendered as the StatefulSet's `volumeClaimTemplates`. Requires `deploymentType: "StatefulSet"` - setting it on a Deployment or DaemonSet fails at render time rather than being silently dropped (use `volumes`/`extraVolumes` there instead). |
| worker_ocr_layout.volumeMounts | list | `[{"mountPath":"/tmp","name":"tmp"}]` | List of mounts to add (normally used with `volumes` or `volumeClaims`). Prefer this for mounts the chart itself always needs; use `extraVolumeMounts` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to the `/tmp` mount backing the hardened `readOnlyRootFilesystem` default (see `volumes` above). |
| worker_ocr_layout.volumes | list | `[{"emptyDir":{},"name":"tmp"}]` | List of volumes to add. Prefer this for volumes the chart itself always needs (e.g. security-hardening `emptyDir`s); use `extraVolumes` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to a `/tmp` `emptyDir`, which is what makes the default `securityContext.readOnlyRootFilesystem: true` usable - drop it only if you also relax that. Helm replaces lists wholesale rather than merging them, so overriding this key means restating the entries you want to keep. |

#### Autoscaling

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_layout.autoscaling.enabled | bool | `false` | Enable Horizontal Pod Autoscaler for the app. |
| worker_ocr_layout.autoscaling.maxReplicas | int | `3` | Maximum number of replicas for the app. |
| worker_ocr_layout.autoscaling.minReplicas | int | `1` | Minimum number of replicas for the app. |
| worker_ocr_layout.autoscaling.targetCPUUtilizationPercentage | int | `80` | Average CPU utilization percentage for the app. |
| worker_ocr_layout.autoscaling.targetMemoryUtilizationPercentage | int | `80` | Average memory utilization percentage for the app. |

#### GrpcRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_layout.grpcRoute.annotations | object | `{}` | Additional GRPCRoute annotations. |
| worker_ocr_layout.grpcRoute.enabled | bool | `false` | Enable a GRPCRoute resource for this service. |
| worker_ocr_layout.grpcRoute.hostnames | list | `[]` | Hostnames for the GRPCRoute to match. |
| worker_ocr_layout.grpcRoute.labels | object | `{}` | Additional GRPCRoute labels. |
| worker_ocr_layout.grpcRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the GRPCRoute to. |
| worker_ocr_layout.grpcRoute.rules | list | `[]` | Routing rules for the GRPCRoute. |

#### HttpRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_layout.httpRoute.annotations | object | `{}` | Additional HTTPRoute annotations. |
| worker_ocr_layout.httpRoute.enabled | bool | `false` | Enable an HTTPRoute resource for this service. |
| worker_ocr_layout.httpRoute.hostnames | list | `[]` | Hostnames for the HTTPRoute to match. |
| worker_ocr_layout.httpRoute.labels | object | `{}` | Additional HTTPRoute labels. |
| worker_ocr_layout.httpRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the HTTPRoute to. |
| worker_ocr_layout.httpRoute.rules | list | `[]` | Routing rules for the HTTPRoute. |

#### Image

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_layout.image.digest | string | `""` | Image digest (`sha256:...`). When set it takes precedence over `tag`, pinning the exact image content so the same release can never resolve to a different build - preferred over a mutable tag for anything you deploy to production. |
| worker_ocr_layout.image.pullPolicy | string | `"IfNotPresent"` | Image pull policy for the app. |
| worker_ocr_layout.image.registry | string | `"ghcr.io"` | Registry to use for the app. |
| worker_ocr_layout.image.repository | string | `"ia-generative/mille-feuille/worker-ocr-layout"` | Repository to use for the app. |
| worker_ocr_layout.image.tag | string | `""` | Tag to use for the app. Overrides the image tag whose default is the chart appVersion. |

#### Ingress

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_layout.ingress.annotations | object | `{}` | Additional ingress annotations. |
| worker_ocr_layout.ingress.className | string | `""` | Defines which ingress controller will implement the resource. |
| worker_ocr_layout.ingress.enabled | bool | `false` | Whether or not ingress should be enabled. |
| worker_ocr_layout.ingress.hosts[0].name | string | `"domain.local"` | Name of the host record. |
| worker_ocr_layout.ingress.hosts[0].paths | list | `[{"backend":{"portNumber":null,"serviceName":""},"path":"/","pathType":"Prefix"}]` | Paths of the host record to manage routing (avoids repeating the same host for multiple paths/backends). |
| worker_ocr_layout.ingress.hosts[0].paths[0].backend.portNumber | string | `nil` | Port used by the backend service linked to the path (leave null to use the app service port). |
| worker_ocr_layout.ingress.hosts[0].paths[0].backend.serviceName | string | `""` | Name of the backend service linked to the path (leave empty to use the app service). |
| worker_ocr_layout.ingress.hosts[0].paths[0].path | string | `"/"` | Path of the host record to manage routing. |
| worker_ocr_layout.ingress.hosts[0].paths[0].pathType | string | `"Prefix"` | Path type of the host record. |
| worker_ocr_layout.ingress.labels | object | `{}` | Additional ingress labels. |
| worker_ocr_layout.ingress.tls | list | `[]` | Enable TLS configuration. |

#### Metrics

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_layout.metrics.enabled | bool | `false` | Deploy metrics service. |
| worker_ocr_layout.metrics.service.annotations | object | `{}` | Metrics service annotations. |
| worker_ocr_layout.metrics.service.labels | object | `{}` | Metrics service labels. |
| worker_ocr_layout.metrics.service.port | int | `9000` | Metrics service port. |
| worker_ocr_layout.metrics.service.portName | string | `"metrics"` | Metrics service port name. |
| worker_ocr_layout.metrics.service.targetPort | int | `9000` | Metrics service target port. |
| worker_ocr_layout.metrics.service.type | string | `"ClusterIP"` | Type of metrics service to create. |
| worker_ocr_layout.metrics.serviceMonitor.annotations | object | `{}` | Prometheus ServiceMonitor annotations. |
| worker_ocr_layout.metrics.serviceMonitor.enabled | bool | `false` | Enable a prometheus ServiceMonitor. |
| worker_ocr_layout.metrics.serviceMonitor.endpoints[0].basicAuth.password | string | `""` | The secret in the service monitor namespace that contains the password for authentication. |
| worker_ocr_layout.metrics.serviceMonitor.endpoints[0].basicAuth.username | string | `""` | The secret in the service monitor namespace that contains the username for authentication. |
| worker_ocr_layout.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.key | string | `""` | Secret key to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| worker_ocr_layout.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.name | string | `""` | Secret name to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| worker_ocr_layout.metrics.serviceMonitor.endpoints[0].honorLabels | bool | `false` | When true, honorLabels preserves the metric’s labels when they collide with the target’s labels. |
| worker_ocr_layout.metrics.serviceMonitor.endpoints[0].interval | string | `"30s"` | Prometheus ServiceMonitor interval. |
| worker_ocr_layout.metrics.serviceMonitor.endpoints[0].metricRelabelings | list | `[]` | Prometheus MetricRelabelConfigs to apply to samples before ingestion. |
| worker_ocr_layout.metrics.serviceMonitor.endpoints[0].path | string | `"/metrics"` | Path used by the Prometheus ServiceMonitor to scrape metrics. |
| worker_ocr_layout.metrics.serviceMonitor.endpoints[0].relabelings | list | `[]` | Prometheus RelabelConfigs to apply to samples before scraping. |
| worker_ocr_layout.metrics.serviceMonitor.endpoints[0].scheme | string | `""` | Prometheus ServiceMonitor scheme. |
| worker_ocr_layout.metrics.serviceMonitor.endpoints[0].scrapeTimeout | string | `"10s"` | Prometheus ServiceMonitor scrapeTimeout. If empty, Prometheus uses the global scrape timeout unless it is less than the target's scrape interval value in which the latter is used. |
| worker_ocr_layout.metrics.serviceMonitor.endpoints[0].selector | object | `{}` | Prometheus ServiceMonitor selector. |
| worker_ocr_layout.metrics.serviceMonitor.endpoints[0].tlsConfig | object | `{}` | Prometheus ServiceMonitor tlsConfig. |
| worker_ocr_layout.metrics.serviceMonitor.labels | object | `{}` | Prometheus ServiceMonitor labels. |

#### NetworkPolicy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_layout.networkPolicy.annotations | object | `{}` | Annotations to be added to the app NetworkPolicy. |
| worker_ocr_layout.networkPolicy.create | bool | `false` | Create NetworkPolicy object for the app. The policy always selects this component's pods only (via its selector labels), never the whole namespace. |
| worker_ocr_layout.networkPolicy.egress | list | `[]` | Egress rules for the NetworkPolicy object. |
| worker_ocr_layout.networkPolicy.ingress | list | `[]` | Ingress rules for the NetworkPolicy object. |
| worker_ocr_layout.networkPolicy.labels | object | `{}` | Labels to be added to the app NetworkPolicy. |
| worker_ocr_layout.networkPolicy.policyTypes | list | `["Ingress"]` | Policy types used in the NetworkPolicy object. |

#### Pdb

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_layout.pdb.annotations | object | `{}` | Annotations to be added to app pdb. |
| worker_ocr_layout.pdb.enabled | bool | `false` | Deploy a PodDisruptionBudget for the app |
| worker_ocr_layout.pdb.labels | object | `{}` | Labels to be added to app pdb. |
| worker_ocr_layout.pdb.maxUnavailable | string | `""` | Number of pods that are unavailable after eviction as number or percentage (eg.: 50%). Has higher precedence over `worker_ocr_layout.pdb.minAvailable`. |
| worker_ocr_layout.pdb.minAvailable | string | `""` | Number of pods that are available after eviction as number or percentage (eg.: 50%). One of `minAvailable` / `maxUnavailable` must be set when `pdb.enabled` is true - a budget of 0 is the same as having no budget at all, so leaving both empty fails at render time. |

#### Probes

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_layout.probes.livenessProbe.failureThreshold | int | `3` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_ocr_layout.probes.livenessProbe.httpGet.path | string | `"/"` | Worker_ocr_layout container healthcheck endpoint (livenessProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_ocr_layout.probes.livenessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_ocr_layout.probes.livenessProbe.initialDelaySeconds | int | `30` | Number of seconds after the container has started before probe is initiated. |
| worker_ocr_layout.probes.livenessProbe.periodSeconds | int | `30` | How often (in seconds) to perform the probe. |
| worker_ocr_layout.probes.livenessProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_ocr_layout.probes.livenessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| worker_ocr_layout.probes.readinessProbe.failureThreshold | int | `2` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_ocr_layout.probes.readinessProbe.httpGet.path | string | `"/"` | Worker_ocr_layout container healthcheck endpoint (readinessProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_ocr_layout.probes.readinessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_ocr_layout.probes.readinessProbe.initialDelaySeconds | int | `10` | Number of seconds after the container has started before probe is initiated. |
| worker_ocr_layout.probes.readinessProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| worker_ocr_layout.probes.readinessProbe.successThreshold | int | `2` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_ocr_layout.probes.readinessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| worker_ocr_layout.probes.startupProbe.failureThreshold | int | `10` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_ocr_layout.probes.startupProbe.httpGet.path | string | `"/"` | Worker_ocr_layout container healthcheck endpoint (startupProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_ocr_layout.probes.startupProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_ocr_layout.probes.startupProbe.initialDelaySeconds | int | `0` | Number of seconds after the container has started before probe is initiated. |
| worker_ocr_layout.probes.startupProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| worker_ocr_layout.probes.startupProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_ocr_layout.probes.startupProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |

#### Resources

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_layout.resources.limits.cpu | string | `"500m"` | CPU limit for the app. |
| worker_ocr_layout.resources.limits.memory | string | `"2Gi"` | Memory limit for the app. |
| worker_ocr_layout.resources.requests.cpu | string | `"100m"` | CPU request for the app. |
| worker_ocr_layout.resources.requests.memory | string | `"256Mi"` | Memory request for the app. |

#### Service

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_layout.service.enabled | bool | `true` | Whether or not to create a Service for the app. Set to `false` for components that don't accept traffic (e.g. a queue consumer with no `containerPort`). |
| worker_ocr_layout.service.extraPorts | list | `[]` | Extra service ports. |
| worker_ocr_layout.service.nodePort | int | `null` (allocated by Kubernetes) | Port used when type is `NodePort` to expose the service on the given node port. Left empty, Kubernetes allocates one from the configured node-port range, which avoids two releases of this chart colliding on the same hardcoded port. |
| worker_ocr_layout.service.port | int | `80` | Port used by the service. |
| worker_ocr_layout.service.portName | string | `"http"` | Port name used by the service. |
| worker_ocr_layout.service.protocol | string | `"TCP"` | Protocol used by the service. |
| worker_ocr_layout.service.type | string | `"ClusterIP"` | Type of service to create for the app. |

#### ServiceAccount

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_layout.serviceAccount.annotations | object | `{}` | Annotations applied to created service account. |
| worker_ocr_layout.serviceAccount.automountServiceAccountToken | bool | `false` | Should the service account access token be automount in the pod. |
| worker_ocr_layout.serviceAccount.clusterRole.create | bool | `false` | Should the clusterRole be created. |
| worker_ocr_layout.serviceAccount.clusterRole.rules | list | `[]` | ClusterRole rules associated with the service account. |
| worker_ocr_layout.serviceAccount.create | bool | `false` | Create a service account. |
| worker_ocr_layout.serviceAccount.enabled | bool | `false` | Enable the service account. |
| worker_ocr_layout.serviceAccount.name | string | `""` | Service account name. |
| worker_ocr_layout.serviceAccount.role.create | bool | `false` | Should the role be created. |
| worker_ocr_layout.serviceAccount.role.rules | list | `[]` | Role rules associated with the service account. |

#### Strategy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_layout.strategy.rollingUpdate.maxSurge | int | `1` | The maximum number of pods that can be scheduled above the desired number of pods. |
| worker_ocr_layout.strategy.rollingUpdate.maxUnavailable | int | `1` | The maximum number of pods that can be unavailable during the update process. |
| worker_ocr_layout.strategy.type | string | `"RollingUpdate"` | Strategy type used to replace old Pods by new ones, can be `Recreate` or `RollingUpdate`. Only applied when `deploymentType` is "Deployment". |

### WorkerOcrTable

#### General

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_table.affinity | object | `{}` | Affinity used for app pod. |
| worker_ocr_table.args | list | `[]` | Worker_ocr_table container command args. |
| worker_ocr_table.automountServiceAccountToken | bool | `false` | Mount the ServiceAccount token into the app pods. Defaults to false so a compromised container holds no API credentials; the API server does not need the token unless the app actually talks to the Kubernetes API. Applied at pod level so it holds even when `serviceAccount.name` points at an SA that automounts. |
| worker_ocr_table.command | list | `[]` | Worker_ocr_table container command. |
| worker_ocr_table.containerPort | int | `8080` | Worker_ocr_table container port number. Set to `null`/`0` (and disable `service`/probes) for components that don't listen on any port (e.g. a queue consumer). |
| worker_ocr_table.containerPortName | string | `"http"` | Worker_ocr_table container port name. |
| worker_ocr_table.deploymentType | string | `"Deployment"` | Workload kind to deploy the app as. One of "Deployment", "StatefulSet" or "DaemonSet" (validated at render time - an unknown value fails instead of producing a release with no workload). Use the top-level `jobs` / `cronjobs` maps for one-off or scheduled workloads. Some values only apply to certain kinds: `replicaCount`/`autoscaling` and `strategy` are Deployment-only (`autoscaling` also works on a StatefulSet), `volumeClaims`/`extraVolumeClaims` are StatefulSet-only, and `updateStrategy` covers StatefulSet and DaemonSet. |
| worker_ocr_table.dnsConfig | object | `{}` | Pod DNS configuration, merged with `dnsPolicy` by the kubelet. |
| worker_ocr_table.dnsPolicy | string | `""` (`ClusterFirstWithHostNet` when `hostNetwork` is true) | Pod DNS policy. Left empty, it defaults to `ClusterFirstWithHostNet` when `hostNetwork` is true (otherwise a hostNetwork pod silently stops resolving cluster DNS) and to the Kubernetes default `ClusterFirst` when it isn't. |
| worker_ocr_table.enableServiceLinks | bool | `false` | Inject the legacy `{SVC}_SERVICE_HOST`/`_PORT` environment variables for every Service in the namespace. Defaults to false: the variables are rarely used, leak the namespace's topology into every container, and can collide with the app's own configuration. Set to true only for an app that genuinely reads them. |
| worker_ocr_table.enabled | bool | `false` | Déploie le pod d'OCR « tableaux des pages scannées (SLANet_plus) » (OCR_ENGINE=layout de `worker_document`). Désactivé par défaut : il porte un modèle ONNX et n'a de sens qu'avec les autres pods d'OCR. Voir worker/document_process/README.md. |
| worker_ocr_table.env | object | `{}` | Map or array of environment variables to inject into the app container (`valueFrom` supported). |
| worker_ocr_table.envCm | object | `{}` | Map of environment variables to inject into a configmap loaded by the app container (`valueFrom` not supported). |
| worker_ocr_table.envFrom | list | `[]` | Worker_ocr_table container env variables loaded from configmap or secret reference. List or map (merged with `global.envFrom` above, global entries first); see `global.envFrom` for both forms. |
| worker_ocr_table.envSecret | object | `{}` | Map of environment variables to inject into a secret loaded by the app container (`valueFrom` not supported). Values placed here are stored in plain text in the values file AND in the Helm release secret, so use it for non-sensitive-but-secret-shaped config only. For real credentials prefer referencing a Secret you manage elsewhere via `envFrom`, or have an operator materialise it (see the `VaultStaticSecret` example under `extraObjects`). |
| worker_ocr_table.extraContainers | list | `[]` | Extra containers to add to the app pod as sidecars. |
| worker_ocr_table.extraPorts | list | `[]` | Worker_ocr_table extra container ports. |
| worker_ocr_table.extraVolumeClaims | list | `[]` | Additional volumeClaims to add, concatenated with `volumeClaims` above at render time. |
| worker_ocr_table.extraVolumeMounts | list | `[]` | Additional volumeMounts to add, concatenated with `volumeMounts` above at render time. |
| worker_ocr_table.extraVolumes | list | `[]` | Additional volumes to add, concatenated with `volumes` above at render time (e.g. to mount a cert or config from a values override without repeating the chart's own volumes). |
| worker_ocr_table.hostAliases | list | `[]` | Host aliases that will be injected at pod-level into /etc/hosts. |
| worker_ocr_table.hostNetwork | bool | `false` | Share the host network namespace. Container ports then bind directly on the node, so they must not collide with anything else running there. |
| worker_ocr_table.hostPID | bool | `false` | Share the host PID namespace (lets the container see and signal host processes). |
| worker_ocr_table.imagePullSecrets | list | `[]` | Image credentials configuration. |
| worker_ocr_table.initContainers | list | `[]` | Init containers to add to the app pod. |
| worker_ocr_table.nodeSelector | object | `{}` | Default node selector for app. |
| worker_ocr_table.podAnnotations | object | `{}` | Annotations for the app deployed pods. |
| worker_ocr_table.podLabels | object | `{}` | Labels for the app deployed pods. |
| worker_ocr_table.podSecurityContext | object | `{"fsGroup":1000,"fsGroupChangePolicy":"OnRootMismatch","runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000,"seccompProfile":{"type":"RuntimeDefault"}}` | Pod-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard. Rendered via `toYaml`, so any `PodSecurityContext` field is accepted. Adjust the UID/GID to whatever your image actually ships with - `runAsNonRoot` makes the kubelet refuse to start a container that would run as root, which is the intended failure mode rather than something to switch off. Set to `null` to omit the block entirely. |
| worker_ocr_table.priorityClassName | string | `""` | PriorityClass to schedule the pods with (e.g. `system-node-critical` for a node agent that must not be evicted under pressure). |
| worker_ocr_table.replicaCount | int | `1` | The number of application controller pods to run. Ignored when `deploymentType` is "DaemonSet" (one pod per node) or when `autoscaling.enabled` is true. |
| worker_ocr_table.revisionHistoryLimit | int | `10` | Revision history limit for the app. |
| worker_ocr_table.securityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"privileged":false,"readOnlyRootFilesystem":true,"runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000}` | Container-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard: no privilege escalation, no capabilities, immutable root filesystem. Rendered via `toYaml`, so any `SecurityContext` field is accepted. Note `readOnlyRootFilesystem` requires the app to write only to mounted volumes - the default `volumes`/`volumeMounts` below provide an `emptyDir` on /tmp for that reason. Set to `null` to omit the block entirely. |
| worker_ocr_table.terminationGracePeriodSeconds | int | `null` (Kubernetes default of 30) | Grace period, in seconds, given to the pod to shut down cleanly before it is killed. |
| worker_ocr_table.tolerations | list | `[]` | Default tolerations for app. |
| worker_ocr_table.topologySpreadConstraints | list | `[]` | Topology spread constraints used to spread the pods across failure domains. |
| worker_ocr_table.updateStrategy | object | `{}` | Update strategy applied when `deploymentType` is "StatefulSet" or "DaemonSet" (ignored for a Deployment, which uses `strategy` above). Rendered verbatim via `toYaml`, so it takes the native `StatefulSetUpdateStrategy`/`DaemonSetUpdateStrategy` shape of the selected kind; left empty, Kubernetes applies its own default (`RollingUpdate` for both). |
| worker_ocr_table.volumeClaims | list | `[]` | List of volumeClaims to add, rendered as the StatefulSet's `volumeClaimTemplates`. Requires `deploymentType: "StatefulSet"` - setting it on a Deployment or DaemonSet fails at render time rather than being silently dropped (use `volumes`/`extraVolumes` there instead). |
| worker_ocr_table.volumeMounts | list | `[{"mountPath":"/tmp","name":"tmp"}]` | List of mounts to add (normally used with `volumes` or `volumeClaims`). Prefer this for mounts the chart itself always needs; use `extraVolumeMounts` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to the `/tmp` mount backing the hardened `readOnlyRootFilesystem` default (see `volumes` above). |
| worker_ocr_table.volumes | list | `[{"emptyDir":{},"name":"tmp"}]` | List of volumes to add. Prefer this for volumes the chart itself always needs (e.g. security-hardening `emptyDir`s); use `extraVolumes` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to a `/tmp` `emptyDir`, which is what makes the default `securityContext.readOnlyRootFilesystem: true` usable - drop it only if you also relax that. Helm replaces lists wholesale rather than merging them, so overriding this key means restating the entries you want to keep. |

#### Autoscaling

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_table.autoscaling.enabled | bool | `false` | Enable Horizontal Pod Autoscaler for the app. |
| worker_ocr_table.autoscaling.maxReplicas | int | `3` | Maximum number of replicas for the app. |
| worker_ocr_table.autoscaling.minReplicas | int | `1` | Minimum number of replicas for the app. |
| worker_ocr_table.autoscaling.targetCPUUtilizationPercentage | int | `80` | Average CPU utilization percentage for the app. |
| worker_ocr_table.autoscaling.targetMemoryUtilizationPercentage | int | `80` | Average memory utilization percentage for the app. |

#### GrpcRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_table.grpcRoute.annotations | object | `{}` | Additional GRPCRoute annotations. |
| worker_ocr_table.grpcRoute.enabled | bool | `false` | Enable a GRPCRoute resource for this service. |
| worker_ocr_table.grpcRoute.hostnames | list | `[]` | Hostnames for the GRPCRoute to match. |
| worker_ocr_table.grpcRoute.labels | object | `{}` | Additional GRPCRoute labels. |
| worker_ocr_table.grpcRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the GRPCRoute to. |
| worker_ocr_table.grpcRoute.rules | list | `[]` | Routing rules for the GRPCRoute. |

#### HttpRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_table.httpRoute.annotations | object | `{}` | Additional HTTPRoute annotations. |
| worker_ocr_table.httpRoute.enabled | bool | `false` | Enable an HTTPRoute resource for this service. |
| worker_ocr_table.httpRoute.hostnames | list | `[]` | Hostnames for the HTTPRoute to match. |
| worker_ocr_table.httpRoute.labels | object | `{}` | Additional HTTPRoute labels. |
| worker_ocr_table.httpRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the HTTPRoute to. |
| worker_ocr_table.httpRoute.rules | list | `[]` | Routing rules for the HTTPRoute. |

#### Image

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_table.image.digest | string | `""` | Image digest (`sha256:...`). When set it takes precedence over `tag`, pinning the exact image content so the same release can never resolve to a different build - preferred over a mutable tag for anything you deploy to production. |
| worker_ocr_table.image.pullPolicy | string | `"IfNotPresent"` | Image pull policy for the app. |
| worker_ocr_table.image.registry | string | `"ghcr.io"` | Registry to use for the app. |
| worker_ocr_table.image.repository | string | `"ia-generative/mille-feuille/worker-ocr-table"` | Repository to use for the app. |
| worker_ocr_table.image.tag | string | `""` | Tag to use for the app. Overrides the image tag whose default is the chart appVersion. |

#### Ingress

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_table.ingress.annotations | object | `{}` | Additional ingress annotations. |
| worker_ocr_table.ingress.className | string | `""` | Defines which ingress controller will implement the resource. |
| worker_ocr_table.ingress.enabled | bool | `false` | Whether or not ingress should be enabled. |
| worker_ocr_table.ingress.hosts[0].name | string | `"domain.local"` | Name of the host record. |
| worker_ocr_table.ingress.hosts[0].paths | list | `[{"backend":{"portNumber":null,"serviceName":""},"path":"/","pathType":"Prefix"}]` | Paths of the host record to manage routing (avoids repeating the same host for multiple paths/backends). |
| worker_ocr_table.ingress.hosts[0].paths[0].backend.portNumber | string | `nil` | Port used by the backend service linked to the path (leave null to use the app service port). |
| worker_ocr_table.ingress.hosts[0].paths[0].backend.serviceName | string | `""` | Name of the backend service linked to the path (leave empty to use the app service). |
| worker_ocr_table.ingress.hosts[0].paths[0].path | string | `"/"` | Path of the host record to manage routing. |
| worker_ocr_table.ingress.hosts[0].paths[0].pathType | string | `"Prefix"` | Path type of the host record. |
| worker_ocr_table.ingress.labels | object | `{}` | Additional ingress labels. |
| worker_ocr_table.ingress.tls | list | `[]` | Enable TLS configuration. |

#### Metrics

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_table.metrics.enabled | bool | `false` | Deploy metrics service. |
| worker_ocr_table.metrics.service.annotations | object | `{}` | Metrics service annotations. |
| worker_ocr_table.metrics.service.labels | object | `{}` | Metrics service labels. |
| worker_ocr_table.metrics.service.port | int | `9000` | Metrics service port. |
| worker_ocr_table.metrics.service.portName | string | `"metrics"` | Metrics service port name. |
| worker_ocr_table.metrics.service.targetPort | int | `9000` | Metrics service target port. |
| worker_ocr_table.metrics.service.type | string | `"ClusterIP"` | Type of metrics service to create. |
| worker_ocr_table.metrics.serviceMonitor.annotations | object | `{}` | Prometheus ServiceMonitor annotations. |
| worker_ocr_table.metrics.serviceMonitor.enabled | bool | `false` | Enable a prometheus ServiceMonitor. |
| worker_ocr_table.metrics.serviceMonitor.endpoints[0].basicAuth.password | string | `""` | The secret in the service monitor namespace that contains the password for authentication. |
| worker_ocr_table.metrics.serviceMonitor.endpoints[0].basicAuth.username | string | `""` | The secret in the service monitor namespace that contains the username for authentication. |
| worker_ocr_table.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.key | string | `""` | Secret key to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| worker_ocr_table.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.name | string | `""` | Secret name to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| worker_ocr_table.metrics.serviceMonitor.endpoints[0].honorLabels | bool | `false` | When true, honorLabels preserves the metric’s labels when they collide with the target’s labels. |
| worker_ocr_table.metrics.serviceMonitor.endpoints[0].interval | string | `"30s"` | Prometheus ServiceMonitor interval. |
| worker_ocr_table.metrics.serviceMonitor.endpoints[0].metricRelabelings | list | `[]` | Prometheus MetricRelabelConfigs to apply to samples before ingestion. |
| worker_ocr_table.metrics.serviceMonitor.endpoints[0].path | string | `"/metrics"` | Path used by the Prometheus ServiceMonitor to scrape metrics. |
| worker_ocr_table.metrics.serviceMonitor.endpoints[0].relabelings | list | `[]` | Prometheus RelabelConfigs to apply to samples before scraping. |
| worker_ocr_table.metrics.serviceMonitor.endpoints[0].scheme | string | `""` | Prometheus ServiceMonitor scheme. |
| worker_ocr_table.metrics.serviceMonitor.endpoints[0].scrapeTimeout | string | `"10s"` | Prometheus ServiceMonitor scrapeTimeout. If empty, Prometheus uses the global scrape timeout unless it is less than the target's scrape interval value in which the latter is used. |
| worker_ocr_table.metrics.serviceMonitor.endpoints[0].selector | object | `{}` | Prometheus ServiceMonitor selector. |
| worker_ocr_table.metrics.serviceMonitor.endpoints[0].tlsConfig | object | `{}` | Prometheus ServiceMonitor tlsConfig. |
| worker_ocr_table.metrics.serviceMonitor.labels | object | `{}` | Prometheus ServiceMonitor labels. |

#### NetworkPolicy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_table.networkPolicy.annotations | object | `{}` | Annotations to be added to the app NetworkPolicy. |
| worker_ocr_table.networkPolicy.create | bool | `false` | Create NetworkPolicy object for the app. The policy always selects this component's pods only (via its selector labels), never the whole namespace. |
| worker_ocr_table.networkPolicy.egress | list | `[]` | Egress rules for the NetworkPolicy object. |
| worker_ocr_table.networkPolicy.ingress | list | `[]` | Ingress rules for the NetworkPolicy object. |
| worker_ocr_table.networkPolicy.labels | object | `{}` | Labels to be added to the app NetworkPolicy. |
| worker_ocr_table.networkPolicy.policyTypes | list | `["Ingress"]` | Policy types used in the NetworkPolicy object. |

#### Pdb

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_table.pdb.annotations | object | `{}` | Annotations to be added to app pdb. |
| worker_ocr_table.pdb.enabled | bool | `false` | Deploy a PodDisruptionBudget for the app |
| worker_ocr_table.pdb.labels | object | `{}` | Labels to be added to app pdb. |
| worker_ocr_table.pdb.maxUnavailable | string | `""` | Number of pods that are unavailable after eviction as number or percentage (eg.: 50%). Has higher precedence over `worker_ocr_table.pdb.minAvailable`. |
| worker_ocr_table.pdb.minAvailable | string | `""` | Number of pods that are available after eviction as number or percentage (eg.: 50%). One of `minAvailable` / `maxUnavailable` must be set when `pdb.enabled` is true - a budget of 0 is the same as having no budget at all, so leaving both empty fails at render time. |

#### Probes

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_table.probes.livenessProbe.failureThreshold | int | `3` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_ocr_table.probes.livenessProbe.httpGet.path | string | `"/"` | Worker_ocr_table container healthcheck endpoint (livenessProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_ocr_table.probes.livenessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_ocr_table.probes.livenessProbe.initialDelaySeconds | int | `30` | Number of seconds after the container has started before probe is initiated. |
| worker_ocr_table.probes.livenessProbe.periodSeconds | int | `30` | How often (in seconds) to perform the probe. |
| worker_ocr_table.probes.livenessProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_ocr_table.probes.livenessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| worker_ocr_table.probes.readinessProbe.failureThreshold | int | `2` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_ocr_table.probes.readinessProbe.httpGet.path | string | `"/"` | Worker_ocr_table container healthcheck endpoint (readinessProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_ocr_table.probes.readinessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_ocr_table.probes.readinessProbe.initialDelaySeconds | int | `10` | Number of seconds after the container has started before probe is initiated. |
| worker_ocr_table.probes.readinessProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| worker_ocr_table.probes.readinessProbe.successThreshold | int | `2` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_ocr_table.probes.readinessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| worker_ocr_table.probes.startupProbe.failureThreshold | int | `10` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_ocr_table.probes.startupProbe.httpGet.path | string | `"/"` | Worker_ocr_table container healthcheck endpoint (startupProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_ocr_table.probes.startupProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_ocr_table.probes.startupProbe.initialDelaySeconds | int | `0` | Number of seconds after the container has started before probe is initiated. |
| worker_ocr_table.probes.startupProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| worker_ocr_table.probes.startupProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_ocr_table.probes.startupProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |

#### Resources

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_table.resources.limits.cpu | string | `"500m"` | CPU limit for the app. |
| worker_ocr_table.resources.limits.memory | string | `"2Gi"` | Memory limit for the app. |
| worker_ocr_table.resources.requests.cpu | string | `"100m"` | CPU request for the app. |
| worker_ocr_table.resources.requests.memory | string | `"256Mi"` | Memory request for the app. |

#### Service

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_table.service.enabled | bool | `true` | Whether or not to create a Service for the app. Set to `false` for components that don't accept traffic (e.g. a queue consumer with no `containerPort`). |
| worker_ocr_table.service.extraPorts | list | `[]` | Extra service ports. |
| worker_ocr_table.service.nodePort | int | `null` (allocated by Kubernetes) | Port used when type is `NodePort` to expose the service on the given node port. Left empty, Kubernetes allocates one from the configured node-port range, which avoids two releases of this chart colliding on the same hardcoded port. |
| worker_ocr_table.service.port | int | `80` | Port used by the service. |
| worker_ocr_table.service.portName | string | `"http"` | Port name used by the service. |
| worker_ocr_table.service.protocol | string | `"TCP"` | Protocol used by the service. |
| worker_ocr_table.service.type | string | `"ClusterIP"` | Type of service to create for the app. |

#### ServiceAccount

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_table.serviceAccount.annotations | object | `{}` | Annotations applied to created service account. |
| worker_ocr_table.serviceAccount.automountServiceAccountToken | bool | `false` | Should the service account access token be automount in the pod. |
| worker_ocr_table.serviceAccount.clusterRole.create | bool | `false` | Should the clusterRole be created. |
| worker_ocr_table.serviceAccount.clusterRole.rules | list | `[]` | ClusterRole rules associated with the service account. |
| worker_ocr_table.serviceAccount.create | bool | `false` | Create a service account. |
| worker_ocr_table.serviceAccount.enabled | bool | `false` | Enable the service account. |
| worker_ocr_table.serviceAccount.name | string | `""` | Service account name. |
| worker_ocr_table.serviceAccount.role.create | bool | `false` | Should the role be created. |
| worker_ocr_table.serviceAccount.role.rules | list | `[]` | Role rules associated with the service account. |

#### Strategy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_table.strategy.rollingUpdate.maxSurge | int | `1` | The maximum number of pods that can be scheduled above the desired number of pods. |
| worker_ocr_table.strategy.rollingUpdate.maxUnavailable | int | `1` | The maximum number of pods that can be unavailable during the update process. |
| worker_ocr_table.strategy.type | string | `"RollingUpdate"` | Strategy type used to replace old Pods by new ones, can be `Recreate` or `RollingUpdate`. Only applied when `deploymentType` is "Deployment". |

### WorkerOcrVision

#### General

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_vision.affinity | object | `{}` | Affinity used for app pod. |
| worker_ocr_vision.args | list | `[]` | Worker_ocr_vision container command args. |
| worker_ocr_vision.automountServiceAccountToken | bool | `false` | Mount the ServiceAccount token into the app pods. Defaults to false so a compromised container holds no API credentials; the API server does not need the token unless the app actually talks to the Kubernetes API. Applied at pod level so it holds even when `serviceAccount.name` points at an SA that automounts. |
| worker_ocr_vision.command | list | `[]` | Worker_ocr_vision container command. |
| worker_ocr_vision.containerPort | int | `8080` | Worker_ocr_vision container port number. Set to `null`/`0` (and disable `service`/probes) for components that don't listen on any port (e.g. a queue consumer). |
| worker_ocr_vision.containerPortName | string | `"http"` | Worker_ocr_vision container port name. |
| worker_ocr_vision.deploymentType | string | `"Deployment"` | Workload kind to deploy the app as. One of "Deployment", "StatefulSet" or "DaemonSet" (validated at render time - an unknown value fails instead of producing a release with no workload). Use the top-level `jobs` / `cronjobs` maps for one-off or scheduled workloads. Some values only apply to certain kinds: `replicaCount`/`autoscaling` and `strategy` are Deployment-only (`autoscaling` also works on a StatefulSet), `volumeClaims`/`extraVolumeClaims` are StatefulSet-only, and `updateStrategy` covers StatefulSet and DaemonSet. |
| worker_ocr_vision.dnsConfig | object | `{}` | Pod DNS configuration, merged with `dnsPolicy` by the kubelet. |
| worker_ocr_vision.dnsPolicy | string | `""` (`ClusterFirstWithHostNet` when `hostNetwork` is true) | Pod DNS policy. Left empty, it defaults to `ClusterFirstWithHostNet` when `hostNetwork` is true (otherwise a hostNetwork pod silently stops resolving cluster DNS) and to the Kubernetes default `ClusterFirst` when it isn't. |
| worker_ocr_vision.enableServiceLinks | bool | `false` | Inject the legacy `{SVC}_SERVICE_HOST`/`_PORT` environment variables for every Service in the namespace. Defaults to false: the variables are rarely used, leak the namespace's topology into every container, and can collide with the app's own configuration. Set to true only for an app that genuinely reads them. |
| worker_ocr_vision.enabled | bool | `false` | Déploie le pod d'OCR « description des images et tableaux (VLM du hub) » (OCR_ENGINE=layout de `worker_document`). Désactivé par défaut : il porte un modèle ONNX et n'a de sens qu'avec les autres pods d'OCR. Voir worker/document_process/README.md. |
| worker_ocr_vision.env | object | `{}` | Map or array of environment variables to inject into the app container (`valueFrom` supported). |
| worker_ocr_vision.envCm | object | `{}` | Map of environment variables to inject into a configmap loaded by the app container (`valueFrom` not supported). |
| worker_ocr_vision.envFrom | list | `[]` | Worker_ocr_vision container env variables loaded from configmap or secret reference. List or map (merged with `global.envFrom` above, global entries first); see `global.envFrom` for both forms. |
| worker_ocr_vision.envSecret | object | `{}` | Map of environment variables to inject into a secret loaded by the app container (`valueFrom` not supported). Values placed here are stored in plain text in the values file AND in the Helm release secret, so use it for non-sensitive-but-secret-shaped config only. For real credentials prefer referencing a Secret you manage elsewhere via `envFrom`, or have an operator materialise it (see the `VaultStaticSecret` example under `extraObjects`). |
| worker_ocr_vision.extraContainers | list | `[]` | Extra containers to add to the app pod as sidecars. |
| worker_ocr_vision.extraPorts | list | `[]` | Worker_ocr_vision extra container ports. |
| worker_ocr_vision.extraVolumeClaims | list | `[]` | Additional volumeClaims to add, concatenated with `volumeClaims` above at render time. |
| worker_ocr_vision.extraVolumeMounts | list | `[]` | Additional volumeMounts to add, concatenated with `volumeMounts` above at render time. |
| worker_ocr_vision.extraVolumes | list | `[]` | Additional volumes to add, concatenated with `volumes` above at render time (e.g. to mount a cert or config from a values override without repeating the chart's own volumes). |
| worker_ocr_vision.hostAliases | list | `[]` | Host aliases that will be injected at pod-level into /etc/hosts. |
| worker_ocr_vision.hostNetwork | bool | `false` | Share the host network namespace. Container ports then bind directly on the node, so they must not collide with anything else running there. |
| worker_ocr_vision.hostPID | bool | `false` | Share the host PID namespace (lets the container see and signal host processes). |
| worker_ocr_vision.imagePullSecrets | list | `[]` | Image credentials configuration. |
| worker_ocr_vision.initContainers | list | `[]` | Init containers to add to the app pod. |
| worker_ocr_vision.nodeSelector | object | `{}` | Default node selector for app. |
| worker_ocr_vision.podAnnotations | object | `{}` | Annotations for the app deployed pods. |
| worker_ocr_vision.podLabels | object | `{}` | Labels for the app deployed pods. |
| worker_ocr_vision.podSecurityContext | object | `{"fsGroup":1000,"fsGroupChangePolicy":"OnRootMismatch","runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000,"seccompProfile":{"type":"RuntimeDefault"}}` | Pod-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard. Rendered via `toYaml`, so any `PodSecurityContext` field is accepted. Adjust the UID/GID to whatever your image actually ships with - `runAsNonRoot` makes the kubelet refuse to start a container that would run as root, which is the intended failure mode rather than something to switch off. Set to `null` to omit the block entirely. |
| worker_ocr_vision.priorityClassName | string | `""` | PriorityClass to schedule the pods with (e.g. `system-node-critical` for a node agent that must not be evicted under pressure). |
| worker_ocr_vision.replicaCount | int | `1` | The number of application controller pods to run. Ignored when `deploymentType` is "DaemonSet" (one pod per node) or when `autoscaling.enabled` is true. |
| worker_ocr_vision.revisionHistoryLimit | int | `10` | Revision history limit for the app. |
| worker_ocr_vision.securityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"privileged":false,"readOnlyRootFilesystem":true,"runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000}` | Container-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard: no privilege escalation, no capabilities, immutable root filesystem. Rendered via `toYaml`, so any `SecurityContext` field is accepted. Note `readOnlyRootFilesystem` requires the app to write only to mounted volumes - the default `volumes`/`volumeMounts` below provide an `emptyDir` on /tmp for that reason. Set to `null` to omit the block entirely. |
| worker_ocr_vision.terminationGracePeriodSeconds | int | `null` (Kubernetes default of 30) | Grace period, in seconds, given to the pod to shut down cleanly before it is killed. |
| worker_ocr_vision.tolerations | list | `[]` | Default tolerations for app. |
| worker_ocr_vision.topologySpreadConstraints | list | `[]` | Topology spread constraints used to spread the pods across failure domains. |
| worker_ocr_vision.updateStrategy | object | `{}` | Update strategy applied when `deploymentType` is "StatefulSet" or "DaemonSet" (ignored for a Deployment, which uses `strategy` above). Rendered verbatim via `toYaml`, so it takes the native `StatefulSetUpdateStrategy`/`DaemonSetUpdateStrategy` shape of the selected kind; left empty, Kubernetes applies its own default (`RollingUpdate` for both). |
| worker_ocr_vision.volumeClaims | list | `[]` | List of volumeClaims to add, rendered as the StatefulSet's `volumeClaimTemplates`. Requires `deploymentType: "StatefulSet"` - setting it on a Deployment or DaemonSet fails at render time rather than being silently dropped (use `volumes`/`extraVolumes` there instead). |
| worker_ocr_vision.volumeMounts | list | `[{"mountPath":"/tmp","name":"tmp"}]` | List of mounts to add (normally used with `volumes` or `volumeClaims`). Prefer this for mounts the chart itself always needs; use `extraVolumeMounts` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to the `/tmp` mount backing the hardened `readOnlyRootFilesystem` default (see `volumes` above). |
| worker_ocr_vision.volumes | list | `[{"emptyDir":{},"name":"tmp"}]` | List of volumes to add. Prefer this for volumes the chart itself always needs (e.g. security-hardening `emptyDir`s); use `extraVolumes` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to a `/tmp` `emptyDir`, which is what makes the default `securityContext.readOnlyRootFilesystem: true` usable - drop it only if you also relax that. Helm replaces lists wholesale rather than merging them, so overriding this key means restating the entries you want to keep. |

#### Autoscaling

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_vision.autoscaling.enabled | bool | `false` | Enable Horizontal Pod Autoscaler for the app. |
| worker_ocr_vision.autoscaling.maxReplicas | int | `3` | Maximum number of replicas for the app. |
| worker_ocr_vision.autoscaling.minReplicas | int | `1` | Minimum number of replicas for the app. |
| worker_ocr_vision.autoscaling.targetCPUUtilizationPercentage | int | `80` | Average CPU utilization percentage for the app. |
| worker_ocr_vision.autoscaling.targetMemoryUtilizationPercentage | int | `80` | Average memory utilization percentage for the app. |

#### GrpcRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_vision.grpcRoute.annotations | object | `{}` | Additional GRPCRoute annotations. |
| worker_ocr_vision.grpcRoute.enabled | bool | `false` | Enable a GRPCRoute resource for this service. |
| worker_ocr_vision.grpcRoute.hostnames | list | `[]` | Hostnames for the GRPCRoute to match. |
| worker_ocr_vision.grpcRoute.labels | object | `{}` | Additional GRPCRoute labels. |
| worker_ocr_vision.grpcRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the GRPCRoute to. |
| worker_ocr_vision.grpcRoute.rules | list | `[]` | Routing rules for the GRPCRoute. |

#### HttpRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_vision.httpRoute.annotations | object | `{}` | Additional HTTPRoute annotations. |
| worker_ocr_vision.httpRoute.enabled | bool | `false` | Enable an HTTPRoute resource for this service. |
| worker_ocr_vision.httpRoute.hostnames | list | `[]` | Hostnames for the HTTPRoute to match. |
| worker_ocr_vision.httpRoute.labels | object | `{}` | Additional HTTPRoute labels. |
| worker_ocr_vision.httpRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the HTTPRoute to. |
| worker_ocr_vision.httpRoute.rules | list | `[]` | Routing rules for the HTTPRoute. |

#### Image

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_vision.image.digest | string | `""` | Image digest (`sha256:...`). When set it takes precedence over `tag`, pinning the exact image content so the same release can never resolve to a different build - preferred over a mutable tag for anything you deploy to production. |
| worker_ocr_vision.image.pullPolicy | string | `"IfNotPresent"` | Image pull policy for the app. |
| worker_ocr_vision.image.registry | string | `"ghcr.io"` | Registry to use for the app. |
| worker_ocr_vision.image.repository | string | `"ia-generative/mille-feuille/worker-ocr-vision"` | Repository to use for the app. |
| worker_ocr_vision.image.tag | string | `""` | Tag to use for the app. Overrides the image tag whose default is the chart appVersion. |

#### Ingress

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_vision.ingress.annotations | object | `{}` | Additional ingress annotations. |
| worker_ocr_vision.ingress.className | string | `""` | Defines which ingress controller will implement the resource. |
| worker_ocr_vision.ingress.enabled | bool | `false` | Whether or not ingress should be enabled. |
| worker_ocr_vision.ingress.hosts[0].name | string | `"domain.local"` | Name of the host record. |
| worker_ocr_vision.ingress.hosts[0].paths | list | `[{"backend":{"portNumber":null,"serviceName":""},"path":"/","pathType":"Prefix"}]` | Paths of the host record to manage routing (avoids repeating the same host for multiple paths/backends). |
| worker_ocr_vision.ingress.hosts[0].paths[0].backend.portNumber | string | `nil` | Port used by the backend service linked to the path (leave null to use the app service port). |
| worker_ocr_vision.ingress.hosts[0].paths[0].backend.serviceName | string | `""` | Name of the backend service linked to the path (leave empty to use the app service). |
| worker_ocr_vision.ingress.hosts[0].paths[0].path | string | `"/"` | Path of the host record to manage routing. |
| worker_ocr_vision.ingress.hosts[0].paths[0].pathType | string | `"Prefix"` | Path type of the host record. |
| worker_ocr_vision.ingress.labels | object | `{}` | Additional ingress labels. |
| worker_ocr_vision.ingress.tls | list | `[]` | Enable TLS configuration. |

#### Metrics

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_vision.metrics.enabled | bool | `false` | Deploy metrics service. |
| worker_ocr_vision.metrics.service.annotations | object | `{}` | Metrics service annotations. |
| worker_ocr_vision.metrics.service.labels | object | `{}` | Metrics service labels. |
| worker_ocr_vision.metrics.service.port | int | `9000` | Metrics service port. |
| worker_ocr_vision.metrics.service.portName | string | `"metrics"` | Metrics service port name. |
| worker_ocr_vision.metrics.service.targetPort | int | `9000` | Metrics service target port. |
| worker_ocr_vision.metrics.service.type | string | `"ClusterIP"` | Type of metrics service to create. |
| worker_ocr_vision.metrics.serviceMonitor.annotations | object | `{}` | Prometheus ServiceMonitor annotations. |
| worker_ocr_vision.metrics.serviceMonitor.enabled | bool | `false` | Enable a prometheus ServiceMonitor. |
| worker_ocr_vision.metrics.serviceMonitor.endpoints[0].basicAuth.password | string | `""` | The secret in the service monitor namespace that contains the password for authentication. |
| worker_ocr_vision.metrics.serviceMonitor.endpoints[0].basicAuth.username | string | `""` | The secret in the service monitor namespace that contains the username for authentication. |
| worker_ocr_vision.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.key | string | `""` | Secret key to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| worker_ocr_vision.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.name | string | `""` | Secret name to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| worker_ocr_vision.metrics.serviceMonitor.endpoints[0].honorLabels | bool | `false` | When true, honorLabels preserves the metric’s labels when they collide with the target’s labels. |
| worker_ocr_vision.metrics.serviceMonitor.endpoints[0].interval | string | `"30s"` | Prometheus ServiceMonitor interval. |
| worker_ocr_vision.metrics.serviceMonitor.endpoints[0].metricRelabelings | list | `[]` | Prometheus MetricRelabelConfigs to apply to samples before ingestion. |
| worker_ocr_vision.metrics.serviceMonitor.endpoints[0].path | string | `"/metrics"` | Path used by the Prometheus ServiceMonitor to scrape metrics. |
| worker_ocr_vision.metrics.serviceMonitor.endpoints[0].relabelings | list | `[]` | Prometheus RelabelConfigs to apply to samples before scraping. |
| worker_ocr_vision.metrics.serviceMonitor.endpoints[0].scheme | string | `""` | Prometheus ServiceMonitor scheme. |
| worker_ocr_vision.metrics.serviceMonitor.endpoints[0].scrapeTimeout | string | `"10s"` | Prometheus ServiceMonitor scrapeTimeout. If empty, Prometheus uses the global scrape timeout unless it is less than the target's scrape interval value in which the latter is used. |
| worker_ocr_vision.metrics.serviceMonitor.endpoints[0].selector | object | `{}` | Prometheus ServiceMonitor selector. |
| worker_ocr_vision.metrics.serviceMonitor.endpoints[0].tlsConfig | object | `{}` | Prometheus ServiceMonitor tlsConfig. |
| worker_ocr_vision.metrics.serviceMonitor.labels | object | `{}` | Prometheus ServiceMonitor labels. |

#### NetworkPolicy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_vision.networkPolicy.annotations | object | `{}` | Annotations to be added to the app NetworkPolicy. |
| worker_ocr_vision.networkPolicy.create | bool | `false` | Create NetworkPolicy object for the app. The policy always selects this component's pods only (via its selector labels), never the whole namespace. |
| worker_ocr_vision.networkPolicy.egress | list | `[]` | Egress rules for the NetworkPolicy object. |
| worker_ocr_vision.networkPolicy.ingress | list | `[]` | Ingress rules for the NetworkPolicy object. |
| worker_ocr_vision.networkPolicy.labels | object | `{}` | Labels to be added to the app NetworkPolicy. |
| worker_ocr_vision.networkPolicy.policyTypes | list | `["Ingress"]` | Policy types used in the NetworkPolicy object. |

#### Pdb

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_vision.pdb.annotations | object | `{}` | Annotations to be added to app pdb. |
| worker_ocr_vision.pdb.enabled | bool | `false` | Deploy a PodDisruptionBudget for the app |
| worker_ocr_vision.pdb.labels | object | `{}` | Labels to be added to app pdb. |
| worker_ocr_vision.pdb.maxUnavailable | string | `""` | Number of pods that are unavailable after eviction as number or percentage (eg.: 50%). Has higher precedence over `worker_ocr_vision.pdb.minAvailable`. |
| worker_ocr_vision.pdb.minAvailable | string | `""` | Number of pods that are available after eviction as number or percentage (eg.: 50%). One of `minAvailable` / `maxUnavailable` must be set when `pdb.enabled` is true - a budget of 0 is the same as having no budget at all, so leaving both empty fails at render time. |

#### Probes

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_vision.probes.livenessProbe.failureThreshold | int | `3` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_ocr_vision.probes.livenessProbe.httpGet.path | string | `"/"` | Worker_ocr_vision container healthcheck endpoint (livenessProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_ocr_vision.probes.livenessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_ocr_vision.probes.livenessProbe.initialDelaySeconds | int | `30` | Number of seconds after the container has started before probe is initiated. |
| worker_ocr_vision.probes.livenessProbe.periodSeconds | int | `30` | How often (in seconds) to perform the probe. |
| worker_ocr_vision.probes.livenessProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_ocr_vision.probes.livenessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| worker_ocr_vision.probes.readinessProbe.failureThreshold | int | `2` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_ocr_vision.probes.readinessProbe.httpGet.path | string | `"/"` | Worker_ocr_vision container healthcheck endpoint (readinessProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_ocr_vision.probes.readinessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_ocr_vision.probes.readinessProbe.initialDelaySeconds | int | `10` | Number of seconds after the container has started before probe is initiated. |
| worker_ocr_vision.probes.readinessProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| worker_ocr_vision.probes.readinessProbe.successThreshold | int | `2` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_ocr_vision.probes.readinessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| worker_ocr_vision.probes.startupProbe.failureThreshold | int | `10` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_ocr_vision.probes.startupProbe.httpGet.path | string | `"/"` | Worker_ocr_vision container healthcheck endpoint (startupProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_ocr_vision.probes.startupProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_ocr_vision.probes.startupProbe.initialDelaySeconds | int | `0` | Number of seconds after the container has started before probe is initiated. |
| worker_ocr_vision.probes.startupProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| worker_ocr_vision.probes.startupProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_ocr_vision.probes.startupProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |

#### Resources

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_vision.resources.limits.cpu | string | `"500m"` | CPU limit for the app. |
| worker_ocr_vision.resources.limits.memory | string | `"2Gi"` | Memory limit for the app. |
| worker_ocr_vision.resources.requests.cpu | string | `"100m"` | CPU request for the app. |
| worker_ocr_vision.resources.requests.memory | string | `"256Mi"` | Memory request for the app. |

#### Service

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_vision.service.enabled | bool | `true` | Whether or not to create a Service for the app. Set to `false` for components that don't accept traffic (e.g. a queue consumer with no `containerPort`). |
| worker_ocr_vision.service.extraPorts | list | `[]` | Extra service ports. |
| worker_ocr_vision.service.nodePort | int | `null` (allocated by Kubernetes) | Port used when type is `NodePort` to expose the service on the given node port. Left empty, Kubernetes allocates one from the configured node-port range, which avoids two releases of this chart colliding on the same hardcoded port. |
| worker_ocr_vision.service.port | int | `80` | Port used by the service. |
| worker_ocr_vision.service.portName | string | `"http"` | Port name used by the service. |
| worker_ocr_vision.service.protocol | string | `"TCP"` | Protocol used by the service. |
| worker_ocr_vision.service.type | string | `"ClusterIP"` | Type of service to create for the app. |

#### ServiceAccount

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_vision.serviceAccount.annotations | object | `{}` | Annotations applied to created service account. |
| worker_ocr_vision.serviceAccount.automountServiceAccountToken | bool | `false` | Should the service account access token be automount in the pod. |
| worker_ocr_vision.serviceAccount.clusterRole.create | bool | `false` | Should the clusterRole be created. |
| worker_ocr_vision.serviceAccount.clusterRole.rules | list | `[]` | ClusterRole rules associated with the service account. |
| worker_ocr_vision.serviceAccount.create | bool | `false` | Create a service account. |
| worker_ocr_vision.serviceAccount.enabled | bool | `false` | Enable the service account. |
| worker_ocr_vision.serviceAccount.name | string | `""` | Service account name. |
| worker_ocr_vision.serviceAccount.role.create | bool | `false` | Should the role be created. |
| worker_ocr_vision.serviceAccount.role.rules | list | `[]` | Role rules associated with the service account. |

#### Strategy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_ocr_vision.strategy.rollingUpdate.maxSurge | int | `1` | The maximum number of pods that can be scheduled above the desired number of pods. |
| worker_ocr_vision.strategy.rollingUpdate.maxUnavailable | int | `1` | The maximum number of pods that can be unavailable during the update process. |
| worker_ocr_vision.strategy.type | string | `"RollingUpdate"` | Strategy type used to replace old Pods by new ones, can be `Recreate` or `RollingUpdate`. Only applied when `deploymentType` is "Deployment". |

### WorkerRender

#### General

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_render.affinity | object | `{}` | Affinity used for app pod. |
| worker_render.args | list | `[]` | Worker_render container command args. |
| worker_render.automountServiceAccountToken | bool | `false` | Mount the ServiceAccount token into the app pods. Defaults to false so a compromised container holds no API credentials; the API server does not need the token unless the app actually talks to the Kubernetes API. Applied at pod level so it holds even when `serviceAccount.name` points at an SA that automounts. |
| worker_render.command | list | `[]` | Worker_render container command. |
| worker_render.containerPort | int | `8080` | Worker_render container port number. Set to `null`/`0` (and disable `service`/probes) for components that don't listen on any port (e.g. a queue consumer). |
| worker_render.containerPortName | string | `"http"` | Worker_render container port name. |
| worker_render.deploymentType | string | `"Deployment"` | Workload kind to deploy the app as. One of "Deployment", "StatefulSet" or "DaemonSet" (validated at render time - an unknown value fails instead of producing a release with no workload). Use the top-level `jobs` / `cronjobs` maps for one-off or scheduled workloads. Some values only apply to certain kinds: `replicaCount`/`autoscaling` and `strategy` are Deployment-only (`autoscaling` also works on a StatefulSet), `volumeClaims`/`extraVolumeClaims` are StatefulSet-only, and `updateStrategy` covers StatefulSet and DaemonSet. |
| worker_render.dnsConfig | object | `{}` | Pod DNS configuration, merged with `dnsPolicy` by the kubelet. |
| worker_render.dnsPolicy | string | `""` (`ClusterFirstWithHostNet` when `hostNetwork` is true) | Pod DNS policy. Left empty, it defaults to `ClusterFirstWithHostNet` when `hostNetwork` is true (otherwise a hostNetwork pod silently stops resolving cluster DNS) and to the Kubernetes default `ClusterFirst` when it isn't. |
| worker_render.enableServiceLinks | bool | `false` | Inject the legacy `{SVC}_SERVICE_HOST`/`_PORT` environment variables for every Service in the namespace. Defaults to false: the variables are rarely used, leak the namespace's topology into every container, and can collide with the app's own configuration. Set to true only for an app that genuinely reads them. |
| worker_render.env | object | `{}` | Map or array of environment variables to inject into the app container (`valueFrom` supported). |
| worker_render.envCm | object | `{}` | Map of environment variables to inject into a configmap loaded by the app container (`valueFrom` not supported). |
| worker_render.envFrom | list | `[]` | Worker_render container env variables loaded from configmap or secret reference. List or map (merged with `global.envFrom` above, global entries first); see `global.envFrom` for both forms. |
| worker_render.envSecret | object | `{}` | Map of environment variables to inject into a secret loaded by the app container (`valueFrom` not supported). Values placed here are stored in plain text in the values file AND in the Helm release secret, so use it for non-sensitive-but-secret-shaped config only. For real credentials prefer referencing a Secret you manage elsewhere via `envFrom`, or have an operator materialise it (see the `VaultStaticSecret` example under `extraObjects`). |
| worker_render.extraContainers | list | `[]` | Extra containers to add to the app pod as sidecars. |
| worker_render.extraPorts | list | `[]` | Worker_render extra container ports. |
| worker_render.extraVolumeClaims | list | `[]` | Additional volumeClaims to add, concatenated with `volumeClaims` above at render time. |
| worker_render.extraVolumeMounts | list | `[]` | Additional volumeMounts to add, concatenated with `volumeMounts` above at render time. |
| worker_render.extraVolumes | list | `[]` | Additional volumes to add, concatenated with `volumes` above at render time (e.g. to mount a cert or config from a values override without repeating the chart's own volumes). |
| worker_render.hostAliases | list | `[]` | Host aliases that will be injected at pod-level into /etc/hosts. |
| worker_render.hostNetwork | bool | `false` | Share the host network namespace. Container ports then bind directly on the node, so they must not collide with anything else running there. |
| worker_render.hostPID | bool | `false` | Share the host PID namespace (lets the container see and signal host processes). |
| worker_render.imagePullSecrets | list | `[]` | Image credentials configuration. |
| worker_render.initContainers | list | `[]` | Init containers to add to the app pod. |
| worker_render.nodeSelector | object | `{}` | Default node selector for app. |
| worker_render.podAnnotations | object | `{}` | Annotations for the app deployed pods. |
| worker_render.podLabels | object | `{}` | Labels for the app deployed pods. |
| worker_render.podSecurityContext | object | `{"fsGroup":1000,"fsGroupChangePolicy":"OnRootMismatch","runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000,"seccompProfile":{"type":"RuntimeDefault"}}` | Pod-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard. Rendered via `toYaml`, so any `PodSecurityContext` field is accepted. Adjust the UID/GID to whatever your image actually ships with - `runAsNonRoot` makes the kubelet refuse to start a container that would run as root, which is the intended failure mode rather than something to switch off. Set to `null` to omit the block entirely. |
| worker_render.priorityClassName | string | `""` | PriorityClass to schedule the pods with (e.g. `system-node-critical` for a node agent that must not be evicted under pressure). |
| worker_render.replicaCount | int | `1` | The number of application controller pods to run. Ignored when `deploymentType` is "DaemonSet" (one pod per node) or when `autoscaling.enabled` is true. |
| worker_render.revisionHistoryLimit | int | `10` | Revision history limit for the app. |
| worker_render.securityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"privileged":false,"readOnlyRootFilesystem":true,"runAsGroup":1000,"runAsNonRoot":true,"runAsUser":1000}` | Container-level security context. Defaults to a hardened baseline that satisfies the `restricted` Pod Security Standard: no privilege escalation, no capabilities, immutable root filesystem. Rendered via `toYaml`, so any `SecurityContext` field is accepted. Note `readOnlyRootFilesystem` requires the app to write only to mounted volumes - the default `volumes`/`volumeMounts` below provide an `emptyDir` on /tmp for that reason. Set to `null` to omit the block entirely. |
| worker_render.terminationGracePeriodSeconds | int | `null` (Kubernetes default of 30) | Grace period, in seconds, given to the pod to shut down cleanly before it is killed. |
| worker_render.tolerations | list | `[]` | Default tolerations for app. |
| worker_render.topologySpreadConstraints | list | `[]` | Topology spread constraints used to spread the pods across failure domains. |
| worker_render.updateStrategy | object | `{}` | Update strategy applied when `deploymentType` is "StatefulSet" or "DaemonSet" (ignored for a Deployment, which uses `strategy` above). Rendered verbatim via `toYaml`, so it takes the native `StatefulSetUpdateStrategy`/`DaemonSetUpdateStrategy` shape of the selected kind; left empty, Kubernetes applies its own default (`RollingUpdate` for both). |
| worker_render.volumeClaims | list | `[]` | List of volumeClaims to add, rendered as the StatefulSet's `volumeClaimTemplates`. Requires `deploymentType: "StatefulSet"` - setting it on a Deployment or DaemonSet fails at render time rather than being silently dropped (use `volumes`/`extraVolumes` there instead). |
| worker_render.volumeMounts | list | `[{"mountPath":"/tmp","name":"tmp"}]` | List of mounts to add (normally used with `volumes` or `volumeClaims`). Prefer this for mounts the chart itself always needs; use `extraVolumeMounts` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to the `/tmp` mount backing the hardened `readOnlyRootFilesystem` default (see `volumes` above). |
| worker_render.volumes | list | `[{"emptyDir":{},"name":"tmp"}]` | List of volumes to add. Prefer this for volumes the chart itself always needs (e.g. security-hardening `emptyDir`s); use `extraVolumes` below for anything you add on top, so overriding one doesn't require repeating the other. Defaults to a `/tmp` `emptyDir`, which is what makes the default `securityContext.readOnlyRootFilesystem: true` usable - drop it only if you also relax that. Helm replaces lists wholesale rather than merging them, so overriding this key means restating the entries you want to keep. |

#### Autoscaling

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_render.autoscaling.enabled | bool | `false` | Enable Horizontal Pod Autoscaler for the app. |
| worker_render.autoscaling.maxReplicas | int | `3` | Maximum number of replicas for the app. |
| worker_render.autoscaling.minReplicas | int | `1` | Minimum number of replicas for the app. |
| worker_render.autoscaling.targetCPUUtilizationPercentage | int | `80` | Average CPU utilization percentage for the app. |
| worker_render.autoscaling.targetMemoryUtilizationPercentage | int | `80` | Average memory utilization percentage for the app. |

#### GrpcRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_render.grpcRoute.annotations | object | `{}` | Additional GRPCRoute annotations. |
| worker_render.grpcRoute.enabled | bool | `false` | Enable a GRPCRoute resource for this service. |
| worker_render.grpcRoute.hostnames | list | `[]` | Hostnames for the GRPCRoute to match. |
| worker_render.grpcRoute.labels | object | `{}` | Additional GRPCRoute labels. |
| worker_render.grpcRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the GRPCRoute to. |
| worker_render.grpcRoute.rules | list | `[]` | Routing rules for the GRPCRoute. |

#### HttpRoute

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_render.httpRoute.annotations | object | `{}` | Additional HTTPRoute annotations. |
| worker_render.httpRoute.enabled | bool | `false` | Enable an HTTPRoute resource for this service. |
| worker_render.httpRoute.hostnames | list | `[]` | Hostnames for the HTTPRoute to match. |
| worker_render.httpRoute.labels | object | `{}` | Additional HTTPRoute labels. |
| worker_render.httpRoute.parentRefs | list | `[]` | Parent references (Gateways) to attach the HTTPRoute to. |
| worker_render.httpRoute.rules | list | `[]` | Routing rules for the HTTPRoute. |

#### Image

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_render.image.digest | string | `""` | Image digest (`sha256:...`). When set it takes precedence over `tag`, pinning the exact image content so the same release can never resolve to a different build - preferred over a mutable tag for anything you deploy to production. |
| worker_render.image.pullPolicy | string | `"IfNotPresent"` | Image pull policy for the app. |
| worker_render.image.registry | string | `"ghcr.io"` | Registry to use for the app. |
| worker_render.image.repository | string | `"ia-generative/mille-feuille/worker-document-render"` | Repository to use for the app. |
| worker_render.image.tag | string | `""` | Tag to use for the app. Overrides the image tag whose default is the chart appVersion. |

#### Ingress

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_render.ingress.annotations | object | `{}` | Additional ingress annotations. |
| worker_render.ingress.className | string | `""` | Defines which ingress controller will implement the resource. |
| worker_render.ingress.enabled | bool | `false` | Whether or not ingress should be enabled. |
| worker_render.ingress.hosts[0].name | string | `"domain.local"` | Name of the host record. |
| worker_render.ingress.hosts[0].paths | list | `[{"backend":{"portNumber":null,"serviceName":""},"path":"/","pathType":"Prefix"}]` | Paths of the host record to manage routing (avoids repeating the same host for multiple paths/backends). |
| worker_render.ingress.hosts[0].paths[0].backend.portNumber | string | `nil` | Port used by the backend service linked to the path (leave null to use the app service port). |
| worker_render.ingress.hosts[0].paths[0].backend.serviceName | string | `""` | Name of the backend service linked to the path (leave empty to use the app service). |
| worker_render.ingress.hosts[0].paths[0].path | string | `"/"` | Path of the host record to manage routing. |
| worker_render.ingress.hosts[0].paths[0].pathType | string | `"Prefix"` | Path type of the host record. |
| worker_render.ingress.labels | object | `{}` | Additional ingress labels. |
| worker_render.ingress.tls | list | `[]` | Enable TLS configuration. |

#### Metrics

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_render.metrics.enabled | bool | `false` | Deploy metrics service. |
| worker_render.metrics.service.annotations | object | `{}` | Metrics service annotations. |
| worker_render.metrics.service.labels | object | `{}` | Metrics service labels. |
| worker_render.metrics.service.port | int | `9000` | Metrics service port. |
| worker_render.metrics.service.portName | string | `"metrics"` | Metrics service port name. |
| worker_render.metrics.service.targetPort | int | `9000` | Metrics service target port. |
| worker_render.metrics.service.type | string | `"ClusterIP"` | Type of metrics service to create. |
| worker_render.metrics.serviceMonitor.annotations | object | `{}` | Prometheus ServiceMonitor annotations. |
| worker_render.metrics.serviceMonitor.enabled | bool | `false` | Enable a prometheus ServiceMonitor. |
| worker_render.metrics.serviceMonitor.endpoints[0].basicAuth.password | string | `""` | The secret in the service monitor namespace that contains the password for authentication. |
| worker_render.metrics.serviceMonitor.endpoints[0].basicAuth.username | string | `""` | The secret in the service monitor namespace that contains the username for authentication. |
| worker_render.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.key | string | `""` | Secret key to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| worker_render.metrics.serviceMonitor.endpoints[0].bearerTokenSecret.name | string | `""` | Secret name to mount to read bearer token for scraping targets. The secret needs to be in the same namespace as the service monitor and accessible by the Prometheus Operator. |
| worker_render.metrics.serviceMonitor.endpoints[0].honorLabels | bool | `false` | When true, honorLabels preserves the metric’s labels when they collide with the target’s labels. |
| worker_render.metrics.serviceMonitor.endpoints[0].interval | string | `"30s"` | Prometheus ServiceMonitor interval. |
| worker_render.metrics.serviceMonitor.endpoints[0].metricRelabelings | list | `[]` | Prometheus MetricRelabelConfigs to apply to samples before ingestion. |
| worker_render.metrics.serviceMonitor.endpoints[0].path | string | `"/metrics"` | Path used by the Prometheus ServiceMonitor to scrape metrics. |
| worker_render.metrics.serviceMonitor.endpoints[0].relabelings | list | `[]` | Prometheus RelabelConfigs to apply to samples before scraping. |
| worker_render.metrics.serviceMonitor.endpoints[0].scheme | string | `""` | Prometheus ServiceMonitor scheme. |
| worker_render.metrics.serviceMonitor.endpoints[0].scrapeTimeout | string | `"10s"` | Prometheus ServiceMonitor scrapeTimeout. If empty, Prometheus uses the global scrape timeout unless it is less than the target's scrape interval value in which the latter is used. |
| worker_render.metrics.serviceMonitor.endpoints[0].selector | object | `{}` | Prometheus ServiceMonitor selector. |
| worker_render.metrics.serviceMonitor.endpoints[0].tlsConfig | object | `{}` | Prometheus ServiceMonitor tlsConfig. |
| worker_render.metrics.serviceMonitor.labels | object | `{}` | Prometheus ServiceMonitor labels. |

#### NetworkPolicy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_render.networkPolicy.annotations | object | `{}` | Annotations to be added to the app NetworkPolicy. |
| worker_render.networkPolicy.create | bool | `false` | Create NetworkPolicy object for the app. The policy always selects this component's pods only (via its selector labels), never the whole namespace. |
| worker_render.networkPolicy.egress | list | `[]` | Egress rules for the NetworkPolicy object. |
| worker_render.networkPolicy.ingress | list | `[]` | Ingress rules for the NetworkPolicy object. |
| worker_render.networkPolicy.labels | object | `{}` | Labels to be added to the app NetworkPolicy. |
| worker_render.networkPolicy.policyTypes | list | `["Ingress"]` | Policy types used in the NetworkPolicy object. |

#### Pdb

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_render.pdb.annotations | object | `{}` | Annotations to be added to app pdb. |
| worker_render.pdb.enabled | bool | `false` | Deploy a PodDisruptionBudget for the app |
| worker_render.pdb.labels | object | `{}` | Labels to be added to app pdb. |
| worker_render.pdb.maxUnavailable | string | `""` | Number of pods that are unavailable after eviction as number or percentage (eg.: 50%). Has higher precedence over `worker_render.pdb.minAvailable`. |
| worker_render.pdb.minAvailable | string | `""` | Number of pods that are available after eviction as number or percentage (eg.: 50%). One of `minAvailable` / `maxUnavailable` must be set when `pdb.enabled` is true - a budget of 0 is the same as having no budget at all, so leaving both empty fails at render time. |

#### Probes

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_render.probes.livenessProbe.failureThreshold | int | `3` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_render.probes.livenessProbe.httpGet.path | string | `"/"` | Worker_render container healthcheck endpoint (livenessProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_render.probes.livenessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_render.probes.livenessProbe.initialDelaySeconds | int | `30` | Number of seconds after the container has started before probe is initiated. |
| worker_render.probes.livenessProbe.periodSeconds | int | `30` | How often (in seconds) to perform the probe. |
| worker_render.probes.livenessProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_render.probes.livenessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| worker_render.probes.readinessProbe.failureThreshold | int | `2` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_render.probes.readinessProbe.httpGet.path | string | `"/"` | Worker_render container healthcheck endpoint (readinessProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_render.probes.readinessProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_render.probes.readinessProbe.initialDelaySeconds | int | `10` | Number of seconds after the container has started before probe is initiated. |
| worker_render.probes.readinessProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| worker_render.probes.readinessProbe.successThreshold | int | `2` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_render.probes.readinessProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |
| worker_render.probes.startupProbe.failureThreshold | int | `10` | Minimum consecutive failures for the probe to be considered failed after having succeeded. |
| worker_render.probes.startupProbe.httpGet.path | string | `"/"` | Worker_render container healthcheck endpoint (startupProbe is defined using `toYaml` so it is possible to override it completely). |
| worker_render.probes.startupProbe.httpGet.port | int | `8080` | Port to use for healthcheck (defaults to container port). |
| worker_render.probes.startupProbe.initialDelaySeconds | int | `0` | Number of seconds after the container has started before probe is initiated. |
| worker_render.probes.startupProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe. |
| worker_render.probes.startupProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed. |
| worker_render.probes.startupProbe.timeoutSeconds | int | `5` | Number of seconds after which the probe times out. |

#### Resources

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_render.resources.limits.cpu | string | `"2"` | CPU limit for the app. |
| worker_render.resources.limits.memory | string | `"3Gi"` | Memory limit for the app: two concurrent LibreOffice conversions (see `--concurrency` in the image CMD). |
| worker_render.resources.requests.cpu | string | `"250m"` | CPU request for the app. |
| worker_render.resources.requests.memory | string | `"1Gi"` | Memory request for the app. LibreOffice starts a process per conversion (a few hundred MB each). |

#### Service

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_render.service.enabled | bool | `true` | Whether or not to create a Service for the app. Set to `false` for components that don't accept traffic (e.g. a queue consumer with no `containerPort`). |
| worker_render.service.extraPorts | list | `[]` | Extra service ports. |
| worker_render.service.nodePort | int | `null` (allocated by Kubernetes) | Port used when type is `NodePort` to expose the service on the given node port. Left empty, Kubernetes allocates one from the configured node-port range, which avoids two releases of this chart colliding on the same hardcoded port. |
| worker_render.service.port | int | `80` | Port used by the service. |
| worker_render.service.portName | string | `"http"` | Port name used by the service. |
| worker_render.service.protocol | string | `"TCP"` | Protocol used by the service. |
| worker_render.service.type | string | `"ClusterIP"` | Type of service to create for the app. |

#### ServiceAccount

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_render.serviceAccount.annotations | object | `{}` | Annotations applied to created service account. |
| worker_render.serviceAccount.automountServiceAccountToken | bool | `false` | Should the service account access token be automount in the pod. |
| worker_render.serviceAccount.clusterRole.create | bool | `false` | Should the clusterRole be created. |
| worker_render.serviceAccount.clusterRole.rules | list | `[]` | ClusterRole rules associated with the service account. |
| worker_render.serviceAccount.create | bool | `false` | Create a service account. |
| worker_render.serviceAccount.enabled | bool | `false` | Enable the service account. |
| worker_render.serviceAccount.name | string | `""` | Service account name. |
| worker_render.serviceAccount.role.create | bool | `false` | Should the role be created. |
| worker_render.serviceAccount.role.rules | list | `[]` | Role rules associated with the service account. |

#### Strategy

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| worker_render.strategy.rollingUpdate.maxSurge | int | `1` | The maximum number of pods that can be scheduled above the desired number of pods. |
| worker_render.strategy.rollingUpdate.maxUnavailable | int | `1` | The maximum number of pods that can be unavailable during the update process. |
| worker_render.strategy.type | string | `"RollingUpdate"` | Strategy type used to replace old Pods by new ones, can be `Recreate` or `RollingUpdate`. Only applied when `deploymentType` is "Deployment". |

## Sources

**Source code:**

* <https://github.com/IA-Generative/mille-feuille>

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)

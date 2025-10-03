import kopf
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Загружаем конфигурацию Kubernetes (in-cluster или из kubeconfig)
try:
    config.load_incluster_config()
    print("Using in-cluster config")
except config.ConfigException:
    config.load_kube_config()
    print("Using kubeconfig file")

# Инициализируем API клиенты
apps_v1 = client.AppsV1Api()
core_v1 = client.CoreV1Api()
rbac_api = client.RbacAuthorizationV1Api()

# Функция для создания ссылки на владельца (owner reference)
def get_owner_reference(name, uid):
    return [client.V1OwnerReference(
        api_version="otus.homework/v1",
        kind="mysql",
        name=name,
        uid=uid,
        controller=True,
        block_owner_deletion=True
    )]

def create_or_update_secret(namespace, name, password, owner_references):
    metadata = client.V1ObjectMeta(name=f"{name}-secret", owner_references=owner_references)
    secret = client.V1Secret(metadata=metadata, string_data={"MYSQL_ROOT_PASSWORD": password})
    try:
        core_v1.create_namespaced_secret(namespace, secret)
    except ApiException as e:
        if e.status == 409:
            core_v1.replace_namespaced_secret(f"{name}-secret", namespace, secret)
        else:
            raise

def ensure_service_account(namespace, name, owner_references):
    try:
        core_v1.read_namespaced_service_account(name, namespace)
    except ApiException as e:
        if e.status == 404:
            sa = client.V1ServiceAccount(metadata=client.V1ObjectMeta(name=name, owner_references=owner_references))
            core_v1.create_namespaced_service_account(namespace, sa)
        else:
            raise

@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    settings.networking.error_backoffs = [10, 20, 30]

@kopf.on.create('otus.homework', 'v1', 'mysqls')
def create_mysql(spec, name, namespace, uid, **kwargs):
    image = spec.get('image')
    database = spec.get('database')
    password = spec.get('password')
    storage_size = spec.get('storage_size')

    owner_refs = get_owner_reference(name, uid)

    create_or_update_secret(namespace, name, password, owner_refs)

    pvc = client.V1PersistentVolumeClaim(
        metadata=client.V1ObjectMeta(name=f'{name}-pvc', owner_references=owner_refs),
        spec=client.V1PersistentVolumeClaimSpec(
            access_modes=['ReadWriteOnce'],
            resources=client.V1ResourceRequirements(
                requests={'storage': storage_size}
            )
        )
    )
    try:
        core_v1.create_namespaced_persistent_volume_claim(namespace=namespace, body=pvc)
    except ApiException as e:
        if e.status != 409:
            raise

    ensure_service_account(namespace, "mysql", owner_refs)

    container = client.V1Container(
        name='mysql',
        image=image,
        env=[
            client.V1EnvVar(
                name='MYSQL_ROOT_PASSWORD',
                value_from=client.V1EnvVarSource(
                    secret_key_ref=client.V1SecretKeySelector(
                        name=f"{name}-secret",
                        key="MYSQL_ROOT_PASSWORD"
                    )
                )
            ),
            client.V1EnvVar(name='MYSQL_DATABASE', value=database),
        ],
        ports=[client.V1ContainerPort(container_port=3306)],
        volume_mounts=[client.V1VolumeMount(
            mount_path='/var/lib/mysql',
            name='mysql-storage'
        )]
    )
    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels={'app': name}, owner_references=owner_refs),
        spec=client.V1PodSpec(containers=[container], volumes=[
            client.V1Volume(
                name='mysql-storage',
                persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                    claim_name=f'{name}-pvc'
                )
            )
        ])
    )
    spec_deployment = client.V1DeploymentSpec(
        replicas=1,
        selector=client.V1LabelSelector(match_labels={'app': name}),
        template=template
    )
    deployment = client.V1Deployment(
        metadata=client.V1ObjectMeta(name=name, owner_references=owner_refs),
        spec=spec_deployment
    )
    try:
        apps_v1.create_namespaced_deployment(namespace=namespace, body=deployment)
    except ApiException as e:
        if e.status != 409:
            raise

    service = client.V1Service(
        metadata=client.V1ObjectMeta(name=name, owner_references=owner_refs),
        spec=client.V1ServiceSpec(
            selector={'app': name},
            ports=[client.V1ServicePort(port=3306, target_port=3306)],
            type='ClusterIP'
        )
    )
    try:
        core_v1.create_namespaced_service(namespace=namespace, body=service)
    except ApiException as e:
        if e.status != 409:
            raise

    cluster_role = client.V1ClusterRole(
        metadata=client.V1ObjectMeta(name=name),
        rules=[
            client.V1PolicyRule(
                api_groups=["otus.homework"],
                resources=["mysqls", "mysqls/status"],
                verbs=["get", "list", "watch", "create", "update", "patch", "delete"]
            ),
            client.V1PolicyRule(
                api_groups=[""],
                resources=["services", "persistentvolumes", "persistentvolumeclaims"],
                verbs=["create", "delete", "get", "list", "watch", "update", "patch"]
            )
        ]
    )
    try:
        rbac_api.create_cluster_role(body=cluster_role)
    except ApiException as e:
        if e.status == 409:
            rbac_api.replace_cluster_role(name, cluster_role)
        else:
            raise

    cluster_role_binding = client.V1ClusterRoleBinding(
        metadata=client.V1ObjectMeta(name=name),
        subjects=[
            client.RbacV1Subject(
                kind="ServiceAccount",
                name="mysql",
                namespace=namespace
            )
        ],
        role_ref=client.V1RoleRef(
            api_group="rbac.authorization.k8s.io",
            kind="ClusterRole",
            name=name
        )
    )
    try:
        rbac_api.create_cluster_role_binding(body=cluster_role_binding)
    except ApiException as e:
        if e.status == 409:
            rbac_api.replace_cluster_role_binding(name, cluster_role_binding)
        else:
            raise

@kopf.on.delete('otus.homework', 'v1', 'mysqls')
def delete_mysql(name, namespace, **kwargs):
    try:
        apps_v1.delete_namespaced_deployment(name=name, namespace=namespace)
    except ApiException as e:
        if e.status != 404:
            raise

    try:
        core_v1.delete_namespaced_service(name=name, namespace=namespace)
    except ApiException as e:
        if e.status != 404:
            raise

    try:
        core_v1.delete_namespaced_persistent_volume_claim(name=f'{name}-pvc', namespace=namespace)
    except ApiException as e:
        if e.status != 404:
            raise
            
    try:
        core_v1.delete_namespaced_secret(name=f'{name}-secret', namespace=namespace)
    except ApiException as e:
        if e.status != 404:
            raise

    try:
        rbac_api.delete_cluster_role(name)
    except ApiException as e:
        if e.status != 404:
            raise

    try:
        rbac_api.delete_cluster_role_binding(name)
    except ApiException as e:
        if e.status != 404:
            raise
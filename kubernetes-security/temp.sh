1. #test cd
kubectl -n homework create token cd --duration=24h > token
#kubeconf
CLUSTER_NAME=$(kubectl config view --minify -o jsonpath='{.clusters[0].name}')
SERVER=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')
CA_FILE=$(kubectl config view --raw -o jsonpath="{.clusters[?(@.name==\"$CLUSTER_NAME\")].cluster.certificate-authority}")
NAMESPACE=homework
SA=cd
KUBECONFIG_OUT=./cd-kubeconfig
if [ -n "$CA_FILE" ]; then
  CA_DATA=$(base64 -w0 < "$CA_FILE")
else
  CA_DATA=""
fi
TOKEN=$(cat token)
cat > cd-kubeconfig <<EOF
apiVersion: v1
kind: Config
clusters:
- name: ${CLUSTER_NAME}
  cluster:
    server: ${SERVER}
    certificate-authority-data: ${CA_DATA}
contexts:
- name: ${SA}-${NAMESPACE}@${CLUSTER_NAME}
  context:
    cluster: ${CLUSTER_NAME}
    namespace: ${NAMESPACE}
    user: ${SA}-${NAMESPACE}
current-context: ${SA}-${NAMESPACE}@${CLUSTER_NAME}
users:
- name: ${SA}-${NAMESPACE}
  user:
    token: ${TOKEN}
EOF

curl -k https://$SERVER/api/v1/pods -H "Authorization: Bearer $TOKEN"

#pod
2.
curl \
--cacert /var/run/secrets/kubernetes.io/serviceaccount/ca.crt \
-H "Authorization: Bearer $(cat /var/run/secrets/kubernetes.io/serviceaccount/token)"  \
https://kubernetes.default.svc/metrics | grep -v '^#' | wc -l 

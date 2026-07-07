# Argo Runtime Resources

This directory contains the cluster-side artifact repository configuration used
by generated SemT workflows. It is intentionally separate from generated
Workflow YAML and from the I2T-backend deployment bundle.

Apply `artifact-repositories.yaml` in the workflow namespace and create:

- `minio-artifact-credentials` with `accesskey` and `secretkey`
- `semt-runtime-credentials` with `username` and `password`

The committed Secret files are examples only. The `test/test` SemT account is
for the local validation milestone and must be replaced before production use.

Validate the rendered ConfigMap without a cluster:

```sh
kubectl kustomize . | kubeconform -strict -summary
```

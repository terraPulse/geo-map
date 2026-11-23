# Architecture

The registry is a separate system from tile serving.

```text
browser
  |  Cognito hosted UI, authorization code + PKCE, no client secret
  |  access token only on calls to the admin API
  v
CloudFront default domain  -->  private S3 console
  |
  |  cross-origin, JWT authorizer
  v
API Gateway HTTP API  -->  Lambda  -->  DynamoDB staging table
                              |
                              |  does not call
                              v
                    performance-branch test API (not deployed here)
                    /map/{tag}/{z}/{x}/{y}.png
```

Publishing updates one DynamoDB item and an audit item. The Lambda role can read and write that table. It cannot delete items, scan, read S3, or call Cognito admin APIs.

Synthetic fixtures are inserted by a CloudFormation custom resource when the staging table does not already contain those tags. They are marked `synthetic: true` and `inventory: synthetic-fixture`. The console does not embed the catalog.

Legacy `setting.ini` JSON and `color.txt` can be imported and exported as text. Import creates a draft and refuses an existing tag. Export returns text and sets `written: false`.

The dataset schema is `geo-map.layer-registry.v1` in `management/contracts/`. The parent copies it into the interfaces branch before shared use.

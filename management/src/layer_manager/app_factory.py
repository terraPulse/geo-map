"""Wire settings to a repository and the HTTP API."""

from .build_jobs import BuildService, MemoryBuildStore
from .dynamodb_repository import DynamoRepository, boto3_client
from .errors import ConfigurationError
from .http_api import Api, build_service
from .renderer_preview import RendererPreview
from .repository import FileRepository, MemoryRepository


def build_repository(settings, dynamo_client=None):
    if settings.repository == "memory":
        return MemoryRepository()
    if settings.repository == "file":
        if not settings.file_root:
            raise ConfigurationError("File repository requires LAYER_MANAGER_FILE_ROOT.")
        return FileRepository(settings.file_root)
    if settings.repository == "dynamodb":
        client = dynamo_client if dynamo_client is not None else boto3_client(settings.dynamodb_region)
        return DynamoRepository(client, settings.dynamodb_table)
    raise ConfigurationError("Unknown LAYER_MANAGER_REPOSITORY.")


def build_api(settings, dynamo_client=None, repository=None, build_store=None, renderer_invoker=None):
    repo = repository if repository is not None else build_repository(settings, dynamo_client=dynamo_client)
    service = build_service(repo, settings)
    root = settings.file_root or "/tmp/layer-manager-builds"
    builds = BuildService(build_store or MemoryBuildStore(), settings, service, root)
    preview = RendererPreview(settings, invoker=renderer_invoker)
    return Api(service, settings, builds=builds, preview=preview)

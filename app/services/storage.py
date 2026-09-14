import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from boto3.dynamodb.conditions import Key

from config import get_settings

logger = logging.getLogger(__name__)

class Storage:

    def __init__(self, client, table_name: Optional[str] = None):
        settings = get_settings()
        self.table_name = table_name or settings.vpc_table
        self.table = client.Table(self._table_name()) if hasattr(client, "Table") else client

    def _table_name(self) -> str:
        if not self.table_name:
            raise ValueError("DynamoDB table is not set, use the DDB_TABLE_NAME env variable")
        return self.table_name

    @staticmethod
    def _clean(data: Any) -> Any:
        return json.loads(json.dumps(data or {}, default=str))

    def _build_item(self, vpc_id: str, resource_id: str, data: dict) -> dict:
        item = {
            "vpc_id": vpc_id,
            "resource_key": resource_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        item.update(self._clean(data))
        return item

    def insert(self, vpc_id: str, resource_id: str, data: dict) -> dict:
        item = self._build_item(vpc_id, resource_id, data)
        self.table.put_item(Item=item)
        logger.info("Inserted %s in %s", resource_id, self.table_name)
        return item

    def insert_many(self, vpc_id: str, records: list[tuple[str, dict]]) -> list[dict]:
        items = [
            self._build_item(vpc_id, resource_id, data) for resource_id, data in records
        ]
        if not items:
            return []

        with self.table.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)

        logger.info("Inserted %s records in %s", len(items), self.table_name)
        return items

    def get_by_id(self, vpc_id: str, resource_key: Optional[str] = None) -> Optional[dict]:
        response = self.table.get_item(
            Key={"vpc_id": vpc_id, "resource_key": resource_key or vpc_id}
        )
        return response.get("Item")

    def list_all(self, vpc_id: str) -> list[dict]:
        items = []
        request = {"KeyConditionExpression": Key("vpc_id").eq(vpc_id)}
        while True:
            response = self.table.query(**request)
            items.extend(response.get("Items", []))
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                return items
            request["ExclusiveStartKey"] = last_key

    def delete(self, vpc_id: str, resource_id: str) -> None:
        self.table.delete_item(Key={"vpc_id": vpc_id, "resource_key": resource_id})
        logger.info("Deleted %s from %s", resource_id, self.table_name)

    def delete_many(self, vpc_id: str, resource_ids: list[str]) -> list[str]:
        resource_ids = list(resource_ids or [])
        if not resource_ids:
            return []

        with self.table.batch_writer() as batch:
            for resource_id in resource_ids:
                batch.delete_item(Key={"vpc_id": vpc_id, "resource_key": resource_id})

        logger.info("Deleted %s records from %s", len(resource_ids), self.table_name)
        return resource_ids

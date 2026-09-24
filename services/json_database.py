import os
import json
import uuid
import tempfile
import hashlib
import datetime
from config import Config

class JSONDatabase:
    def __init__(self, table_name):
        self.table_name = table_name
        self.dir_path = os.path.join(Config.DATA_DIR, table_name)
        os.makedirs(self.dir_path, exist_ok=True)

    def _get_file_path(self, record_id):
        return os.path.join(self.dir_path, f"{record_id}.json")

    def generate_id(self, prefix=""):
        return f"{prefix}_{uuid.uuid4().hex[:12]}" if prefix else uuid.uuid4().hex[:12]

    def create(self, data, record_id=None, prefix=""):
        """Creates a new record with a unique ID."""
        if not record_id:
            record_id = self.generate_id(prefix)
        data['id'] = record_id
        self.save(record_id, data)
        return record_id

    def save(self, record_id, data):
        """Saves data to a JSON file atomically."""
        file_path = self._get_file_path(record_id)
        # Atomic write: write to temp file, then replace
        fd, temp_path = tempfile.mkstemp(dir=self.dir_path)
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=4)
        os.replace(temp_path, file_path)

    def get(self, record_id):
        """Reads a record by ID. Returns None if not found."""
        file_path = self._get_file_path(record_id)
        if not os.path.exists(file_path):
            return None
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return None

    def get_all(self):
        """Returns all records in the table."""
        records = []
        if not os.path.exists(self.dir_path):
            return records
            
        for filename in os.listdir(self.dir_path):
            if filename.endswith(".json"):
                record_id = filename[:-5]
                record = self.get(record_id)
                if record:
                    records.append(record)
        return records

    def update(self, record_id, updates):
        """Updates an existing record with new data."""
        record = self.get(record_id)
        if record:
            record.update(updates)
            self.save(record_id, record)
            return True
        return False

    def delete(self, record_id):
        """Deletes a record."""
        file_path = self._get_file_path(record_id)
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False

    def find(self, **kwargs):
        """Finds records matching the given key-value pairs."""
        results = []
        for record in self.get_all():
            match = True
            for key, value in kwargs.items():
                if record.get(key) != value:
                    match = False
                    break
            if match:
                results.append(record)
        return results

    def find_one(self, **kwargs):
        """Finds the first record matching the given key-value pairs."""
        for record in self.get_all():
            match = True
            for key, value in kwargs.items():
                if record.get(key) != value:
                    match = False
                    break
            if match:
                return record
        return None


class UniqueIndex:
    """Persistent, atomic uniqueness constraint for the JSON document store.

    JSON files have no native indexes.  Each indexed value gets a separate
    reservation file created with O_EXCL, which is the filesystem equivalent of
    a UNIQUE constraint: two concurrent requests cannot reserve the same key.
    """
    def __init__(self, name):
        self.name = name
        self.dir_path = os.path.join(Config.DATA_DIR, '_unique_indexes', name)
        os.makedirs(self.dir_path, exist_ok=True)

    def _path(self, value):
        digest = hashlib.sha256(value.encode('utf-8')).hexdigest()
        return os.path.join(self.dir_path, f'{digest}.json')

    def reserve(self, value, owner_id):
        value = str(value)
        record = {
            'value': value,
            'owner_id': owner_id,
            'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        try:
            fd = os.open(self._path(value), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            existing = self.get(value)
            return bool(existing and existing.get('owner_id') == owner_id)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(record, handle)
            return True
        except Exception:
            try:
                os.unlink(self._path(value))
            except OSError:
                pass
            raise

    def get(self, value):
        try:
            with open(self._path(str(value)), 'r', encoding='utf-8') as handle:
                return json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def release(self, value, owner_id):
        existing = self.get(value)
        if not existing or existing.get('owner_id') != owner_id:
            return False
        try:
            os.unlink(self._path(str(value)))
            return True
        except FileNotFoundError:
            return False

"""
🚀 ENTERPRISE CUSTOM STORAGE BACKENDS
Robust storage backends for production use with Google Cloud Storage.
"""
from storages.backends.gcloud import GoogleCloudStorage
from urllib.parse import urljoin


class PublicGoogleCloudStorage(GoogleCloudStorage):
    """
    Custom Google Cloud Storage backend that returns public URLs without signing.
    
    This is the ENTERPRISE solution for buckets with uniform bucket-level access
    and public read permissions. It avoids the private key requirement for signed URLs.
    
    Use this when:
    - Your bucket has uniform bucket-level access enabled
    - Your bucket allows public read access (allUsers: roles/storage.objectViewer)
    - You don't need temporary/expiring URLs
    - You want maximum performance (no signing overhead)
    """
    
    def url(self, name):
        """
        Return the public URL to access a given file from the storage.
        
        This overrides the default behavior that tries to generate signed URLs,
        which requires private keys that aren't available with compute engine credentials.
        
        Args:
            name: The name of the file to get the URL for
            
        Returns:
            A direct public URL to the file in Google Cloud Storage
        """
        # Construct the direct public URL
        # Format: https://storage.googleapis.com/{bucket_name}/{file_path}
        return f"https://storage.googleapis.com/{self.bucket_name}/{name}"


class PrivateGoogleCloudStorage(GoogleCloudStorage):
    """
    Custom Google Cloud Storage backend for private files.
    
    Use this for files that should NOT be publicly accessible.
    This still requires proper service account credentials with private keys.
    """
    
    # This would use signed URLs - only use if you have service account keys
    pass


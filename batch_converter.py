"""
Batch Converter Module
Handles folder-based file processing, recursive file scanning, and result packaging
for Oracle SQL to Databricks SQL conversion.
"""

import os
import zipfile
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class BatchConverterResult:
    """Encapsulates batch conversion results"""
    
    def __init__(self, folder_name: str = ""):
        self.successful_conversions: Dict[str, str] = {}  # relative_path -> converted_sql
        self.failed_conversions: Dict[str, str] = {}      # relative_path -> error_message
        self.total_files: int = 0
        self.processed_files: int = 0
        self.folder_name: str = folder_name
    
    def add_success(self, relative_path: str, converted_sql: str):
        """Record successful conversion"""
        self.successful_conversions[relative_path] = converted_sql
        self.processed_files += 1
    
    def add_failure(self, relative_path: str, error_message: str):
        """Record failed conversion"""
        self.failed_conversions[relative_path] = error_message
        self.processed_files += 1
    
    def get_summary(self) -> str:
        """Return human-readable summary"""
        return (
            f"Processed {self.processed_files}/{self.total_files} files\n"
            f"✓ Successful: {len(self.successful_conversions)}\n"
            f"✗ Failed: {len(self.failed_conversions)}"
        )


class BatchConverter:
    """
    Handles batch conversion of Oracle SQL files from uploaded folders.
    Preserves folder structure and maintains error isolation.
    """
    
    SUPPORTED_EXTENSIONS = {'.sql', '.txt', '.ddl'}
    
    def __init__(self, migration_ai):
        """
        Initialize batch converter with migration AI instance
        
        Args:
            migration_ai: MigrationAI instance for conversions
        """
        self.migration_ai = migration_ai
    
    def build_file_structure(self, uploaded_files: List) -> Tuple[str, List[Dict], str]:
        """
        Build folder structure from uploaded files and infer folder name.
        
        Args:
            uploaded_files: List of Streamlit UploadedFile objects
            
        Returns:
            Tuple of (temp_base_dir, file_list, inferred_folder_name)
            file_list contains dicts with 'full_path', 'relative_path', 'filename'
        """
        if not uploaded_files:
            return "", [], ""
        
        temp_base_dir = tempfile.mkdtemp()
        files = []
        folder_names = set()
        
        # Process each uploaded file
        for uploaded_file in uploaded_files:
            # Get the relative path from the uploaded file name
            # UploadedFile.name preserves folder structure when using folder upload
            file_name = uploaded_file.name
            
            # Extract potential folder structure from file path
            path_parts = Path(file_name).parts
            
            # First part is typically the root folder name (from folder selection)
            if len(path_parts) > 1:
                folder_names.add(path_parts[0])
                # Preserve the entire relative path structure
                relative_path = os.path.join(*path_parts)
            else:
                # Single file without folder structure
                relative_path = file_name
            
            # Check if file extension is supported (case-insensitive)
            if Path(file_name).suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                logger.debug(f"Skipping unsupported file type: {file_name}")
                continue
            
            # Create full path and parent directories
            full_path = os.path.join(temp_base_dir, relative_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            # Write file content
            try:
                uploaded_file.seek(0)
                with open(full_path, 'wb') as f:
                    f.write(uploaded_file.read())
                
                files.append({
                    'full_path': full_path,
                    'relative_path': relative_path,
                    'filename': Path(file_name).name
                })
                logger.debug(f"Staged file: {relative_path}")
            except Exception as e:
                logger.error(f"Failed to stage file {file_name}: {e}")
        
        # Infer folder name from uploaded files (deterministic)
        if folder_names:
            # Use the most common folder name, or first one if equal
            inferred_folder_name = sorted(folder_names)[0]  # Deterministic: alphabetical order
        else:
            # Fallback for flat file uploads
            inferred_folder_name = "uploaded_folder"
        
        logger.info(f"Detected folder name: {inferred_folder_name}, Total files: {len(files)}")
        
        return temp_base_dir, sorted(files), inferred_folder_name
    
    def convert_file(self, file_path: str, relative_path: str) -> Tuple[bool, str]:
        """
        Convert single SQL file using existing migration logic.
        
        Args:
            file_path: Full path to SQL file
            relative_path: Relative path (for tracking)
            
        Returns:
            Tuple of (success: bool, result: str)
            - On success: (True, converted_sql)
            - On failure: (False, error_message)
        """
        try:
            # Read source file
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                oracle_sql = f.read()
            
            if not oracle_sql.strip():
                return False, f"File is empty: {relative_path}"
            
            # Use existing migration logic
            result = self.migration_ai.migrate_schema(oracle_sql)
            
            # Handle different result types
            if isinstance(result, list):
                result = "\n".join(map(str, result))
            elif not isinstance(result, str):
                result = str(result)
            
            # Strip out any "Changes and Enhancements" or explanatory sections
            if "### Changes and Enhancements" in result:
                result = result.split("### Changes and Enhancements")[0].strip()
            
            # Remove markdown code fences if present
            if "```sql" in result:
                import re
                sql_match = re.search(r"```sql(.*?)```", result, re.DOTALL)
                if sql_match:
                    result = sql_match.group(1).strip()
            
            return True, result
            
        except Exception as e:
            error_msg = f"Conversion failed: {str(e)}"
            logger.error(f"Error converting {relative_path}: {error_msg}")
            return False, error_msg
    
    
    def extract_zip(self, zip_path: str) -> Tuple[str, List[Dict], str]:
        """
        Extract ZIP file and build file list.
        
        Args:
            zip_path: Path to ZIP file
            
        Returns:
            Tuple of (temp_base_dir, file_list, folder_name)
            file_list contains dicts with 'full_path', 'relative_path'
        """
        temp_base_dir = tempfile.mkdtemp()
        
        try:
            # Extract ZIP
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_base_dir)
        except Exception as e:
            logger.error(f"Error extracting ZIP: {e}")
            return temp_base_dir, [], "unknown"
        
        # Scan for supported files
        files = []
        folder_names = set()
        
        for root, dirs, filenames in os.walk(temp_base_dir):
            for filename in filenames:
                if Path(filename).suffix.lower() in self.SUPPORTED_EXTENSIONS:
                    full_path = os.path.join(root, filename)
                    # Calculate relative path
                    relative_path = os.path.relpath(full_path, temp_base_dir)
                    
                    # Extract top-level folder for naming
                    path_parts = Path(relative_path).parts
                    if len(path_parts) > 1:
                        folder_names.add(path_parts[0])
                    
                    files.append({
                        'full_path': full_path,
                        'relative_path': relative_path
                    })
        
        # Determine folder name - use alphabetically first if multiple
        folder_name = sorted(folder_names)[0] if folder_names else Path(zip_path).stem
        
        return temp_base_dir, files, folder_name
    
    def process_batch(self, zip_path: str, progress_callback=None) -> BatchConverterResult:
        """
        Process all files in a ZIP archive with error isolation.
        
        Args:
            zip_path: Path to ZIP file
            progress_callback: Optional callback for progress updates
                             Called with (current, total, filename)
            
        Returns:
            BatchConverterResult with conversion results
        """
        result = BatchConverterResult()
        
        # Extract ZIP and build file list
        temp_base_dir, files, folder_name = self.extract_zip(zip_path)
        result.folder_name = folder_name
        result.total_files = len(files)
        
        if not files:
            logger.warning("No supported SQL files found in ZIP")
            return result
        
        # Process each file
        for idx, file_info in enumerate(files):
            relative_path = file_info['relative_path']
            full_path = file_info['full_path']
            
            # Progress callback
            if progress_callback:
                progress_callback(idx + 1, len(files), relative_path)
            
            # Convert file
            success, content = self.convert_file(full_path, relative_path)
            
            if success:
                result.add_success(relative_path, content)
            else:
                result.add_failure(relative_path, content)
        
        # Store temp directory for cleanup
        self.temp_base_dir = temp_base_dir
        
        return result
    
    def rebuild_output_structure(self, result: BatchConverterResult, source_temp_dir: str) -> str:
        """
        Rebuild folder structure with converted files.
        Uses deterministic output folder naming: converted_<folder_name>
        
        Args:
            result: BatchConverterResult with conversions
            source_temp_dir: Temp directory with uploaded files (unused, for compatibility)
            
        Returns:
            Path to output directory containing converted_<folder_name> folder
        """
        # Create output root with deterministic naming
        converted_folder_name = f"converted_{result.folder_name}"
        output_root = tempfile.mkdtemp()
        output_dir = os.path.join(output_root, converted_folder_name)
        
        try:
            os.makedirs(output_dir, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create output directory: {e}")
            raise
        
        # Write converted files maintaining structure
        for relative_path, converted_sql in result.successful_conversions.items():
            output_file_path = os.path.join(output_dir, relative_path)
            
            try:
                # Ensure parent directory exists
                os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
                
                # Normalize extension to .sql if needed
                if not output_file_path.lower().endswith('.sql'):
                    base_path = os.path.splitext(output_file_path)[0]
                    output_file_path = base_path + '.sql'
                
                # Write converted content
                with open(output_file_path, 'w', encoding='utf-8') as f:
                    f.write(converted_sql)
                
                logger.debug(f"Written converted file: {relative_path}")
            except Exception as e:
                logger.error(f"Failed to write converted file {relative_path}: {e}")
        
        # Write error log if there are failures
        if result.failed_conversions:
            error_log_path = os.path.join(output_dir, 'errors.txt')
            try:
                with open(error_log_path, 'w', encoding='utf-8') as f:
                    f.write("Oracle SQL to Databricks SQL Conversion - Error Log\n")
                    f.write("=" * 70 + "\n")
                    f.write(f"Folder: {result.folder_name}\n")
                    f.write(f"Total Files: {result.total_files}\n")
                    f.write(f"Successful: {len(result.successful_conversions)}\n")
                    f.write(f"Failed: {len(result.failed_conversions)}\n")
                    f.write("=" * 70 + "\n\n")
                    
                    for relative_path, error_msg in sorted(result.failed_conversions.items()):
                        f.write(f"File: {relative_path}\n")
                        f.write(f"Error: {error_msg}\n")
                        f.write("-" * 70 + "\n")
                
                logger.info(f"Created errors.txt with {len(result.failed_conversions)} errors")
            except Exception as e:
                logger.error(f"Failed to create error log: {e}")
        
        return output_dir
    
    def create_output_zip(self, output_dir: str, folder_name: str) -> str:
        """
        Create downloadable ZIP from output directory.
        Uses deterministic naming: converted_<folder_name>.zip
        
        Args:
            output_dir: Directory containing converted_<folder_name> subfolder structure
            folder_name: Original folder name for ZIP naming (deterministic)
            
        Returns:
            Path to created ZIP file
        """
        # Generate deterministic ZIP name
        zip_name = f"converted_{folder_name}.zip"
        output_zip_path = os.path.join(tempfile.gettempdir(), zip_name)
        
        try:
            # Create ZIP preserving the folder structure
            with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Walk the converted folder (which includes converted_<folder_name> as root)
                for root, dirs, files in os.walk(output_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        # Calculate archive name relative to parent of converted folder
                        # This ensures converted_<folder_name>/ appears at root level in ZIP
                        arcname = os.path.relpath(file_path, os.path.dirname(output_dir))
                        zipf.write(file_path, arcname)
            
            logger.info(f"Created ZIP: {zip_name} ({os.path.getsize(output_zip_path) / 1024:.1f}KB)")
            return output_zip_path
        
        except Exception as e:
            logger.error(f"Failed to create output ZIP: {e}")
            raise
    
    def cleanup(self, *paths: str):
        """Clean up temporary directories"""
        for path in paths:
            if path and os.path.exists(path):
                try:
                    shutil.rmtree(path)
                    logger.debug(f"Cleaned up: {path}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup {path}: {e}")

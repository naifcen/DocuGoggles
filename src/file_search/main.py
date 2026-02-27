import os
from typing import Dict, List
from tabulate import tabulate
from tqdm import tqdm
from datetime import datetime
import json
from file_search.text_extractor.text_extractor import TextExtractor
from file_search.file_scanner.scanner import FileScanner
from file_search.search.searcher import ContentSearcher
from file_search.cache.content_cache import ContentCache
if __name__ == "__main__":
    try:
        from file_search.text_extractor.text_extractor import TextExtractor
        from file_search.file_scanner.scanner import FileScanner
        from file_search.search.searcher import ContentSearcher
    except ImportError:
        import sys
        from pathlib import Path
        sys.path.append(str(Path(__file__).parent.parent))
        from file_search.text_extractor.text_extractor import TextExtractor
        from file_search.file_scanner.scanner import FileScanner
        from file_search.search.searcher import ContentSearcher
import os
from typing import Dict, List
from tabulate import tabulate
from tqdm import tqdm
from datetime import datetime
import json
from file_search.search.meili_search_client import MeiliSearchClient




def format_file_count(count: int) -> str:
    """Format file count with thousands separator"""
    return f"{count:,}"

def categorize_extensions(files: Dict[str, List]) -> Dict[str, Dict[str, int]]:
    """Categorize file extensions into groups"""
    categories = {
        'Documents': ['.txt', '.pdf', '.docx'],
        'Images': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico', '.tiff'],
        'Code': ['.py', '.js', '.java', '.cpp', '.h', '.css', '.html', '.ts', '.jsx', '.php'],
        'Archives': ['.zip', '.rar', '.7z', '.tar', '.gz'],
        'Media': ['.mp3', '.mp4', '.wav', '.avi', '.mov', '.ogg'],
        'Data': ['.json', '.xml', '.csv', '.sql', '.db'],
        'Executables': ['.exe', '.dll', '.msi'],
        'Other': []
    }
    
    result = {category: {} for category in categories}
    
    for ext, files_list in files.items():
        categorized = False
        for category, extensions in categories.items():
            if ext.lower() in extensions:
                result[category][ext] = len(files_list)
                categorized = True
                break
        if not categorized:
            result['Other'][ext] = len(files_list)
    
    return result

def extract_and_store_content(files: Dict[str, List], extractor: TextExtractor, content_cache=None):
    """Extract content from supported files, using cache when available"""
    extracted_contents = {}
    total_files = sum(len(files_list) for files_list in files.values())
    files_to_process = []
    cached_files = 0
    
    # First check which files need processing
    for ext, files_list in files.items():
        if extractor.is_supported_extension(ext):
            for file_info in files_list:
                file_path = file_info['path']
                # If we have a cache, check if file is already cached
                if content_cache and content_cache.is_file_cached(file_path):
                    # Need to load this specific document
                    doc_id = content_cache.cache_index.get("files", {}).get(file_path, {}).get("doc_id")
                    if doc_id:
                        doc_path = content_cache._get_document_path(doc_id)
                        try:
                            with open(doc_path, 'r', encoding='utf-8') as f:
                                document = json.load(f)
                                extracted_contents[file_path] = {
                                    'content': document.get('content', ''),
                                    'metadata': document.get('metadata', {})
                                }
                                cached_files += 1
                        except Exception as e:
                            # If we can't load the cached document, process the file again
                            print(f"\nError loading cached document for {file_path}: {e}")
                            files_to_process.append((file_info, ext))
                    else:
                        files_to_process.append((file_info, ext))
                else:
                    # Need to process this file
                    files_to_process.append((file_info, ext))
    
    # Now process only the files that need it
    if files_to_process:
        print(f"\nExtracting content from {len(files_to_process)} files...")
        with tqdm(total=len(files_to_process), desc="Extracting content") as pbar:
            for file_info, ext in files_to_process:
                try:
                    result = extractor.read_file(file_info['path'])
                    extracted_contents[file_info['path']] = {
                        'content': result['content'],
                        'metadata': result['metadata']
                    }
                    # Update cache if we have one
                    if content_cache:
                        content_cache.save_document(file_info['path'], {
                            'content': result['content'],
                            'metadata': result['metadata']
                        })
                except Exception as e:
                    print(f"\nError processing {file_info['name']}: {str(e)}")
                finally:
                    pbar.update(1)
    
    if cached_files > 0:
        print(f"\nLoaded {cached_files} files from cache.")
    
    # Update cache index if available
    if content_cache:
        content_cache.cache_index["last_updated"] = datetime.now().isoformat()
        content_cache._save_index()
    
    return extracted_contents

def print_category_results(category_name: str, extensions: Dict[str, int]):
    """Print results for a specific category"""
    if not extensions:
        return
    
    data = [[ext, format_file_count(count)] for ext, count in 
            sorted(extensions.items(), key=lambda x: x[1], reverse=True)]
    
    print(f"\n{category_name}")
    print("=" * len(category_name))
    print(tabulate(data, headers=['Extension', 'Count'], tablefmt='simple'))
    print(f"Total {category_name.lower()}: {format_file_count(sum(extensions.values()))}")

def display_search_results(results: List[Dict]):
    """Display search results with improved formatting and context"""
    if not results:
        print("\nNo matches found.")
        return
    
    print(f"\nFound matches in {len(results)} files:")
    print("=" * 60)
    
    # Calculate total matches
    total_matches = sum(r.get('match_count', 0) for r in results)
    
    # Group by file extension
    extension_counts = {}
    for result in results:
        ext = result.get('extension', 'unknown')
        extension_counts[ext] = extension_counts.get(ext, 0) + 1
    
    # Print summary
    print(f"Total matches: {total_matches}")
    print("File types: " + ", ".join([f"{ext} ({count})" for ext, count in extension_counts.items()]))
    print("-" * 60)
    
    # Show results with relevance score if available
    for idx, result in enumerate(results, 1):
        file_name = os.path.basename(result['file_path'])
        rel_score = result.get('relevance_score', None)
        score_display = f" (relevance: {rel_score:.2f})" if rel_score is not None else ""
        
        print(f"\n{idx}. File: {file_name}{score_display}")
        print(f"   Path: {result['file_path']}")
        print(f"   Type: {result.get('extension', 'unknown')} | Size: {format_file_size(result.get('file_size', 0))}")
        print(f"   Matches: {result.get('match_count', 0)}")
        
        # Print more detailed context snippets
        print("\n   Context snippets:")
        for i, snippet in enumerate(result.get('snippets', [])[:5], 1):
            # Format the snippet to highlight the match
            formatted_snippet = snippet.replace('[', '\033[1;31m').replace(']', '\033[0m')
            print(f"   {i}. {formatted_snippet}")
        
        remaining = len(result.get('snippets', [])) - 5
        if remaining > 0:
            print(f"   ... and {remaining} more matches")
        print("-" * 60)

def format_file_size(size_in_bytes):
    """Format file size in human-readable format"""
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    elif size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.1f} KB"
    elif size_in_bytes < 1024 * 1024 * 1024:
        return f"{size_in_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_in_bytes / (1024 * 1024 * 1024):.1f} GB"

def main():
    from file_search.cache.content_cache import ContentCache    

    default_dir = os.path.expanduser("~")
    print(f"\nCurrent directory: {default_dir}")
    custom_dir = input("Press Enter to use current directory or enter a new path: ").strip()
    directory_to_scan = custom_dir if custom_dir else default_dir
    
    # Initialize cache
    content_cache = ContentCache()
    
    # Try to load existing cache
    cached_content = content_cache.load_cache()
    cache_stats = content_cache.get_cache_stats()
    
    if cached_content:
        print(f"\nFound cache with {cache_stats['file_count']} files ({format_file_size(cache_stats['total_size'])})")
        use_cache = input("Use cached data? [Y/n]: ").strip().lower()
        
        if use_cache == 'n':
            print("Clearing cache and rescanning...")
            content_cache.clear_cache()
            cached_content = {}
        else:
            print("Using cached data.")
    
    # Initialize scanner and extractor
    scanner = FileScanner(directory_to_scan)
    extractor = TextExtractor()
    
    print(f"\nScanning directory: {directory_to_scan}")
    print("=" * 50)
    
    try:
        print("\nScanning files...")
        # Ask user about PDF processing
        process_pdfs = input("Process PDF files? (This may take longer) [y/N]: ").lower().strip()
        
        supported_extensions = list(extractor.supported_extensions.keys())
        if process_pdfs != 'y':
            supported_extensions.remove('.pdf')
            print("Skipping PDF files.")
        
        files = scanner.scan_directory(supported_extensions)
        
        if not files:
            print("\nNo supported files found in the directory.")
            return
        
        stats = scanner.get_directory_statistics()
        
        # Use the cache-aware content extraction
        extracted_contents = extract_and_store_content(files, extractor, content_cache)
        searcher = ContentSearcher(extracted_contents)
        meili_client = MeiliSearchClient()
        exported_documents = content_cache.export_for_meilisearch()
        print("\nIndexing documents in Meilisearch...")
        meili_client.index_documents(exported_documents)
        while True:
            print("\nOptions:")
            print("1. Search in files")
            print("2. View file statistics")
            print("3. View cache statistics")
            print("4. Clear cache")
            print("5. Exit")
            
            choice = input("\nEnter your choice (1-5): ").strip()
            
            if choice == '1':
                query = input("\nEnter search term: ").strip()
                if query:
                    case_sensitive = input("Case sensitive search? (y/N): ").lower().strip() == 'y'
                    engine_choice = input("Search using (1) Local Memory or (2) Meilisearch? [1/2]: ").strip()
                    if engine_choice == '2':
                        meili_results = meili_client.search(query)
                        if not meili_results:
                            print("\nNo matches found in Meilisearch.")
                        else:
                            print(f"\nFound {len(meili_results)} matches in Meilisearch:")
                            for idx, r in enumerate(meili_results, 1):
                                print(f"{idx}. {r.get('file_name')} - {r.get('file_path')}")
                    else:
                        results = searcher.search(query, case_sensitive=case_sensitive)
                        display_search_results(results)

                    display_search_results(results)
                    
                    # Offer additional filtering
                    if results:
                        filter_option = input("\nApply filters to results? [y/N]: ").lower().strip()
                        if filter_option == 'y':
                            min_matches = input("Minimum matches per file (Enter to skip): ").strip()
                            min_matches = int(min_matches) if min_matches.isdigit() else None
                            
                            extensions = input("Filter by extensions (comma separated, Enter to skip): ").strip()
                            extensions = [ext.strip() for ext in extensions.split(',')] if extensions else None
                            
                            filtered_results = searcher.filter_results(
                                results,
                                min_matches=min_matches,
                                extensions=extensions
                            )
                            
                            print(f"\nFiltered results ({len(filtered_results)} of {len(results)}):")
                            display_search_results(filtered_results)
                else:
                    print("Search term cannot be empty.")
                    
            elif choice == '2':
                categorized_files = categorize_extensions(files)
                for category in categorized_files:
                    print_category_results(category, categorized_files[category])
                
                print("\nSummary")
                print("=======")
                print(f"Total files: {format_file_count(stats['total_files'])}")
                print(f"Total directories: {format_file_count(stats['total_directories'])}")
                print(f"Total size: {format_file_count(stats['total_size'])} bytes")
                print(f"Unique file types: {len(stats['extension_counts'])}")
                print(f"Extracted content from: {len(extracted_contents)} files")
            
            elif choice == '3':
                # Display cache statistics
                cache_stats = content_cache.get_cache_stats()
                print("\nCache Statistics")
                print("===============")
                print(f"Cached files: {cache_stats['file_count']}")
                print(f"Total cache size: {format_file_size(cache_stats['total_size'])}")
                print("File extensions:")
                for ext, count in cache_stats['extensions'].items():
                    print(f"  - {ext}: {count}")
                last_updated = cache_stats.get('last_updated')
                if last_updated:
                    print(f"Last updated: {last_updated}")
            
            elif choice == '4':
                # Clear cache
                confirm = input("Are you sure you want to clear the cache? [y/N]: ").lower().strip()
                if confirm == 'y':
                    content_cache.clear_cache()
                    print("Cache cleared successfully.")
                
            elif choice == '5':
                print("\nGoodbye!")
                break
                
            else:
                print("\nInvalid choice. Please try again.")
                
    except FileNotFoundError:
        print(f"\nError: Directory '{directory_to_scan}' not found.")
    except Exception as e:
        print(f"\nError occurred: {str(e)}")

if __name__ == "__main__":
    main()
# file_search/search/searcher.py

import re
from typing import List, Dict, Any
from pathlib import Path

class ContentSearcher:
    """
    A class for searching text content within files and extracting meaningful snippets.
    """
    
    def __init__(self, extracted_contents: Dict[str, Dict[str, Any]]):
        """
        Initialize the ContentSearcher with extracted file contents.
        
        Args:
            extracted_contents: Dictionary mapping file paths to their content and metadata
        """
        self.extracted_contents = extracted_contents
        
    def search(self, query: str, case_sensitive: bool = False) -> List[Dict[str, Any]]:
        """
        Search for a query string in all extracted text content.
        
        Args:
            query: The search term to look for
            case_sensitive: Whether the search should be case-sensitive
            
        Returns:
            List of dictionaries containing search results with file information and snippets
        """
        results = []
        
        flags = 0 if case_sensitive else re.IGNORECASE
        
        for file_path, file_data in self.extracted_contents.items():
            content = file_data.get('content', '')
            metadata = file_data.get('metadata', {})
            
            # Skip empty content
            if not content:
                continue
                
            # Find all matches
            matches = list(re.finditer(re.escape(query), content, flags))
            
            if matches:
                # Generate context snippets
                snippets = self._generate_snippets(content, matches, context_size=50)
                
                results.append({
                    'file_path': file_path,
                    'file_name': metadata.get('name', Path(file_path).name),
                    'extension': metadata.get('extension', Path(file_path).suffix),
                    'file_size': metadata.get('size', 0),
                    'modified': metadata.get('modified', None),
                    'match_count': len(matches),
                    'snippets': snippets,
                    'relevance_score': self._calculate_relevance(content, query, len(matches))
                })
        
        # Sort results by relevance score
        results.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        return results
    
    def _generate_snippets(self, content: str, matches: List[re.Match], context_size: int = 50) -> List[str]:
        """
        Generate context snippets for each match in the content.
        
        Args:
            content: The text content to extract snippets from
            matches: List of regex match objects
            context_size: Number of characters to include before and after the match
            
        Returns:
            List of snippet strings with highlighting
        """
        snippets = []
        lines = content.split('\n')
        line_indices = [0]
        
        # Calculate line start positions
        pos = 0
        for line in lines:
            pos += len(line) + 1  # +1 for the newline
            line_indices.append(pos)
        
        # Generate a snippet for each match
        for match in matches:
            # Find which line contains the match
            match_start = match.start()
            match_end = match.end()
            match_text = match.group()
            
            # Find the line number that contains this match
            line_num = next((i for i, pos in enumerate(line_indices) if pos > match_start), len(lines)) - 1
            
            # Get the line and determine context boundaries
            line = lines[line_num]
            line_start_pos = line_indices[line_num]
            char_pos_in_line = match_start - line_start_pos
            
            # Create the snippet with highlight
            before = line[:char_pos_in_line]
            after = line[char_pos_in_line + len(match_text):]
            
            # Truncate context if too long
            if len(before) > context_size:
                before = "..." + before[-context_size:]
            if len(after) > context_size:
                after = after[:context_size] + "..."
                
            highlighted_snippet = f"{before}[{match_text}]{after}"
            snippets.append(highlighted_snippet)
            
        return snippets
    
    def _calculate_relevance(self, content: str, query: str, match_count: int) -> float:
        """
        Calculate a relevance score for the search result.
        
        Args:
            content: The text content that was searched
            query: The search term used
            match_count: Number of matches found
            
        Returns:
            Relevance score (higher is more relevant)
        """
        # Basic relevance calculation based on:
        # 1. Number of matches
        # 2. Matches per content length
        # 3. Query length (longer queries are more specific)
        if not content:
            return 0.0
            
        content_words = len(content.split())
        if content_words == 0:
            return 0.0
            
        normalized_matches = min(match_count / 10, 1.0)  # Cap at 1.0
        density_score = match_count / (content_words / 100)  # Matches per 100 words
        query_specificity = min(len(query) / 10, 1.0)  # Cap at 1.0
        
        return normalized_matches * 0.5 + density_score * 0.3 + query_specificity * 0.2
    
    def filter_results(self, results: List[Dict[str, Any]], 
                      min_matches: int = None,
                      extensions: List[str] = None,
                      date_after: Any = None,
                      date_before: Any = None,
                      min_size: int = None,
                      max_size: int = None) -> List[Dict[str, Any]]:
        """
        Filter search results by various criteria.
        
        Args:
            results: Original search results to filter
            min_matches: Minimum number of matches required
            extensions: List of file extensions to include
            date_after: Only include files modified after this date
            date_before: Only include files modified before this date
            min_size: Minimum file size in bytes
            max_size: Maximum file size in bytes
            
        Returns:
            Filtered list of search results
        """
        filtered_results = results.copy()
        
        if min_matches is not None:
            filtered_results = [r for r in filtered_results if r['match_count'] >= min_matches]
            
        if extensions is not None:
            filtered_results = [r for r in filtered_results if r['extension'].lower() in 
                               [ext.lower() for ext in extensions]]
            
        if date_after is not None and hasattr(date_after, 'date'):
            filtered_results = [r for r in filtered_results if r['modified'] and r['modified'] >= date_after]
            
        if date_before is not None and hasattr(date_before, 'date'):
            filtered_results = [r for r in filtered_results if r['modified'] and r['modified'] <= date_before]
            
        if min_size is not None:
            filtered_results = [r for r in filtered_results if r['file_size'] >= min_size]
            
        if max_size is not None:
            filtered_results = [r for r in filtered_results if r['file_size'] <= max_size]
            
        return filtered_results
    
    def get_result_statistics(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate statistics about the search results.
        
        Args:
            results: List of search results
            
        Returns:
            Dictionary with statistics about the results
        """
        if not results:
            return {"total_results": 0}
            
        # Count file types
        extension_counts = {}
        for result in results:
            ext = result['extension']
            extension_counts[ext] = extension_counts.get(ext, 0) + 1
            
        # Calculate total matches
        total_matches = sum(r['match_count'] for r in results)
        
        # Get average file size
        total_size = sum(r['file_size'] for r in results)
        avg_size = total_size / len(results) if results else 0
        
        return {
            "total_results": len(results),
            "total_matches": total_matches,
            "avg_matches_per_file": total_matches / len(results) if results else 0,
            "extension_counts": extension_counts,
            "total_size": total_size,
            "avg_size": avg_size
        }
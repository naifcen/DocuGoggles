import streamlit as st
from meilisearch import Client
from datetime import datetime
import re

# Connect to Meilisearch
client = Client("http://127.0.0.1:7700", "masterKey")
index = client.index("documents")

st.set_page_config(page_title="DocuGoggles Search", layout="wide")
st.title("📂 DocuGoggles Content Search")
st.markdown("🔍 *Search your scanned file contents using smart filters and previews*")

# Highlight style
st.markdown("""
    <style>
    mark, em {
        background-color: #ffe066;
        padding: 2px 4px;
        border-radius: 4px;
        font-style: normal;
    }
    </style>
""", unsafe_allow_html=True)

query = st.text_input("Enter search query:")

# Sidebar Filters
with st.sidebar:
    st.header("🔎 Filters")
    file_types = st.multiselect("File types", [".txt", ".pdf", ".docx", ".png", ".jpg", ".jpeg"])
    min_size = st.slider("Minimum file size (KB)", 0, 1000, 0)
    max_size = st.slider("Maximum file size (KB)", 1, 10000, 5000)

    st.markdown("----")
    st.subheader("🧠 Advanced Filters")
    filename_filter = st.text_input("Filename contains:")
    directory_filter = st.text_input("Parent folder contains:")

    modified_after = st.date_input("Modified after (optional):", value=None)
    modified_before = st.date_input("Modified before (optional):", value=None)

    min_match_count = st.slider("Minimum match count", 0, 20, 0)
    search_content_only = st.checkbox("Search in content only", value=False)
    exact_word_match = st.checkbox("Exact word match", value=False)

# Filter string for Meilisearch
filters = []
if file_types:
    filters.append(" OR ".join([f'extension = "{ext}"' for ext in file_types]))
filters.append(f"size >= {min_size * 1024}")
filters.append(f"size <= {max_size * 1024}")
filter_str = " AND ".join([f"({f})" if 'OR' in f else f for f in filters])

# Perform search
if query:
    try:
        raw = index.search(query.strip(), {
            "filter": filter_str if filters else None,
            "limit": 50,
            "attributesToHighlight": ["content"]
        })

        all_results = raw.get("hits", [])

        # Content-only + exact word filtering
        if search_content_only or exact_word_match:
            if exact_word_match:
                pattern = re.compile(rf"\b{re.escape(query.strip())}\b", re.IGNORECASE)
            else:
                pattern = re.compile(re.escape(query.strip()), re.IGNORECASE)

            all_results = [r for r in all_results if pattern.search(r.get("content", ""))]

        # Post-filtering
        filtered = []
        for res in all_results:
            if filename_filter and filename_filter.lower() not in res.get("file_name", "").lower():
                continue
            if directory_filter and directory_filter.lower() not in res.get("file_path", "").lower():
                continue

            modified_str = res.get("modified")
            if modified_after and modified_str:
                try:
                    if datetime.fromisoformat(modified_str).date() < modified_after:
                        continue
                except:
                    pass
            if modified_before and modified_str:
                try:
                    if datetime.fromisoformat(modified_str).date() > modified_before:
                        continue
                except:
                    pass
            if res.get("match_count", 0) < min_match_count:
                continue

            filtered.append(res)

        st.subheader(f"🔎 Found {len(filtered)} matching file(s)")

        def extract_snippet_from_highlight(highlighted_text: str, context: int = 100) -> str:
            """Extract the first <em> match with context around it."""
            match = re.search(r"<em>(.*?)</em>", highlighted_text, re.IGNORECASE)
            if not match:
                return highlighted_text[:300] + "..."  # fallback

            start = max(match.start() - context, 0)
            end = min(match.end() + context, len(highlighted_text))
            snippet = highlighted_text[start:end]

            # Replace <em> with <mark> for styling
            snippet = re.sub(r"<em>(.*?)</em>", r"<mark>\1</mark>", snippet)
            if start > 0:
                snippet = "..." + snippet
            if end < len(highlighted_text):
                snippet += "..."
            return snippet

        for res in filtered:
            with st.expander(f"📄 {res.get('file_name')} ({res.get('extension')})", expanded=False):
                file_path = res.get('file_path')
                st.code(f"📁 Path: {file_path}", language='text')
                st.markdown(f"**📏 Size:** {res.get('size', 0) / 1024:.1f} KB")
                st.markdown(f"**🕒 Modified:** {res.get('modified')}")
                st.markdown("### 🔦 Preview")

                # Preview Snippet
                highlighted = res.get("_formatted", {}).get("content", "")
                preview = extract_snippet_from_highlight(highlighted)
                if preview:
                    st.write(preview, unsafe_allow_html=True)
                else:
                    st.write("⚠️ Match found, but no snippet preview available.")

                escaped_path = file_path.replace("\\", "\\\\")  # do it before the f-string
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"📋 Copy Path", key=f"copy_{file_path}"):
                        escaped_path = file_path.replace("\\", "\\\\")  # do it before the f-string
                        st.markdown(f"""
                            <script>
                            navigator.clipboard.writeText("{escaped_path}");
                            </script>
                            ✅ Copied!
                        """, unsafe_allow_html=True)

                with col2:
                    if st.button(f"📂 Open File", key=f"open_{file_path}"):
                        import os, subprocess, platform
                        try:
                            if platform.system() == "Windows":
                                os.startfile(file_path)
                            elif platform.system() == "Darwin":  # macOS
                                subprocess.call(["open", file_path])
                            else:  # Linux
                                subprocess.call(["xdg-open", file_path])
                        except Exception as e:
                            st.error(f"Failed to open file: {e}")


    except Exception as e:
        st.error(f"Search failed: {e}")
else:
    st.info("Type a query above to search.") 
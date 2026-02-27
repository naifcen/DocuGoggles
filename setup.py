from setuptools import setup, find_packages

setup(
    name="DocuGoggles",
    version="0.3.2",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "python-magic>=0.4.27",
        "click>=8.0.0",
        "pathlib>=1.0.1",
        "tqdm>=4.65.0",
        "pytesseract>=0.3.10",
        "Pillow>=9.0.0",
        "PyPDF2>=3.0.0",
        "chardet>=5.0.0",
        "python-docx>=0.8.11",  
        "tabulate>=0.9.0", 
        "pystray>=0.19.0"
    ],
    entry_points={
        'console_scripts': [
            'docugoggles=file_search.main:main',
        ],
    },
    author="Naif ALqurashi",
    author_email="Naif.cen@gmail.com",
    description="A tool for scanning and analyzing files in directories",
    long_description="DocuGoggles - A File Search and Analysis Tool",
    long_description_content_type="text/markdown",
    url="https://github.com/Duquesne-Spring-2025-COSC-481/Naif-ALqurashi",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
    license="MIT",
)
from setuptools import setup, find_packages
try:
    from aicommit import __version__ as package_version
except Exception:
    package_version = "0.0.0"

setup(
    name='aicommit',
    version=package_version,
    packages=find_packages(),
    install_requires=[
        'openai',
        'python-dotenv',
        'gitpython',
    ],
    entry_points={
        'console_scripts': [
            'aicommit=aicommit.commit:main',
        ],
    },
    author='Webmech',
    author_email='mike@pricelove.co',
    description='A tool to generate commit messages using OpenAI',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/web-mech/aicommit',
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
)

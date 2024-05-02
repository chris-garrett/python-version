# python-version

Generates next version details based on git tags. Provides Pip and Nuget safe values. 

## Changelog

See: version.py

## Usage

Using json format:

```bash
$ python version.py minor --tag-prefix=myservice-v --format json --json-pretty
{
    "major": 0,
    "minor": 5,
    "patch": 0,
    "commits": 1,
    "hash": "755b0b099e12275918b055b7c41a5b3465caf630",
    "branch": "main",
    "last_tag": "myservice-v0.4.0",
    "last_hash": "8f163b9f59a89553eadb9689d70ebd5eace53603",
    "tag": "myservice-v0.5.0",
    "tag_prefix": "myservice-v",
    "semver": "0.5.0",
    "semver_full": "0.5.0",
    "pep440": "0.5.0",
    "nuget": "0.5.0",
    "timestamp": "20240502T215701Z"
}
```

Using environment variable format with an output prefix:

```bash
$ python version.py minor --tag-prefix=myservice-v --format env --env-prefix BUILD_
BUILD_MAJOR=0
BUILD_MINOR=5
BUILD_PATCH=0
BUILD_COMMITS=1
BUILD_HASH="755b0b099e12275918b055b7c41a5b3465caf630"
BUILD_BRANCH="main"
BUILD_LAST_TAG="myservice-v0.4.0"
BUILD_LAST_HASH="8f163b9f59a89553eadb9689d70ebd5eace53603"
BUILD_TAG="myservice-v0.5.0"
BUILD_TAG_PREFIX="myservice-v"
BUILD_SEMVER="0.5.0"
BUILD_SEMVER_FULL="0.5.0"
BUILD_PEP440="0.5.0"
BUILD_NUGET="0.5.0"
BUILD_TIMESTAMP="20240502T215727Z"
```

Using csv format with an output header:

```bash
$ python version.py minor --tag-prefix=myservice-v --format csv --csv-header
major,minor,patch,commits,hash,branch,last_tag,last_hash,tag,tag_prefix,semver,semver_full,pep440,nuget,timestamp
0,5,0,1,755b0b099e12275918b055b7c41a5b3465caf630,main,myservice-v0.4.0,8f163b9f59a89553eadb9689d70ebd5eace53603,myservice-v0.5.0,myservice-v,0.5.0,0.5.0,0.5.0,0.5.0,20240502T220103Z
```


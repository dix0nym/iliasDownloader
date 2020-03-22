# iliasDownloader

## Installation

1. `git clone https://github.com/dix0nym/iliasDownloader.git`
2. `cd iliasDownloader`
3. `pip install -r requirements.txt`
4. `cp config.sample.json config.json`
5. create `config.json` - see [Configuration](#Configuration)
6. `python iliasDownloader.py`

## Configuration

example configuration for HS-Albsig
```json
{
    "path": "OUTPUT",
    "username": "USERNAME",
    "password": "SECRETPASSWORD",
    "client_id": "HS-ALBSIG",
    "server": "https://elearning.hs-albsig.de/webservice/soap/server.php?wsdl"
}
```

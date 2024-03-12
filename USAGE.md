# Running SunGatherEvo

## Docker

### Basic Operation

```
mkdir config
curl -o config/config.yaml https://raw.githubusercontent.com/ludifu/SunGather/main/SunGather/config-example.yaml
```

Configure `host` and `port` of your inverter in `config/config.yaml`. Then
start the container.

```
docker run -d \
  --name <containername> \
  --network="host" \
  --restart always \
  -v ./config:/config \
  -e TZ=Europe/Berlin \
  ludifu/sungather:latest
```

Make sure the container name does not collide with any other container's name
on your installation. Change the timezone to your location.

You can watch the logs to check whether SunGatherEvo can contact your inverter:

```
docker logs -f <containername>
```

### Using an individual register configuration

```
mkdir registers
curl -o registers/registers-sungrow.yaml https://raw.githubusercontent.com/ludifu/SunGather/main/SunGather/registers-sungrow.yaml
```

Make changes in `registers/registers-sungrow.yaml` if desired. Start the
container with an additional volume for the registers:

```
  -v ./registers:/registers
```

### Using a separate log file

In `config/config.yaml` set the `log_file` parameter to any valid value except
"OFF". Create logs directory:

```
mkdir logs
chmod 777 logs
```

Start the container with a separate volume for the logs:

```
  -v ./logs:/logs
```

### Using the web server export

Start the container with a port mapping:

```
  -p 8080:8080
```

### Complete docker example

```
docker run -d \
  --name <containername> \
  --network="host" \
  --restart always \
  -v ./config:/config \
  -v ./registers:/registers \
  -v ./logs:/logs \
  -p 8080:8080 \
  -e TZ=Europe/Berlin \
  ludifu/sungather:latest
```


### docker compose

```
mkdir sungatherevo
curl -o sungatherevo/config.yaml https://raw.githubusercontent.com/ludifu/SunGather/main/SunGather/config-example.yaml
curl -o sungatherevo/registers-sungrow.yaml https://raw.githubusercontent.com/ludifu/SunGather/main/SunGather/registers-sungrow.yaml
```

Adapt `sungatherevo/config.yaml`.

In the `services` section in your `docker-compose.yml` add:

```
 sungatherevo:
    image: ludifu/sungather:latest
    container_name: sungatherevo
    restart: unless-stopped
    volumes:
      - ./sungatherevo/config.yaml:/config/config.yaml
      - ./sungatherevo/registers-sungrow.yaml:/registers/registers-sungrow.yaml
    environment:
      - TZ=Europe/Berlin
    ports:
      - "8080:8080"
```

> [!NOTE]
> You may need to add a `networks` section within the service.

## Local operation

```
git clone https://github.com/ludifu/SunGather.git
python3 -m venv .venv
source .venv/bin/activate 
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

Edit `Sungather/config-example.yaml` and set at least `host` and `port` of your
inverter. Then start SunGatherEvo:

```
python3 SunGather/sungather.py -v 10 -c SunGather/config-example.yaml -r SunGather/registers-sungrow.yaml
```

To get commandline help run: 

```
python3 SunGather/sungather.py --help
```





# Developing

Get `docker`, `git` and an editor of your choice - *Real Men™* do use `vim` of
course, if only to set them apart from the [quiche
eaters](https://web.archive.org/web/20120206010243/http://www.ee.ryerson.ca/~elf/hack/realmen.html).

Get the code:

```
git clone https://github.com/ludifu/SunGather.git
```

## Using Docker watch

```
curl -o registers/config.yaml https://raw.githubusercontent.com/ludifu/SunGather/main/SunGather/config-example.yaml
curl -o registers/registers-sungrow.yaml https://raw.githubusercontent.com/ludifu/SunGather/main/SunGather/registers-sungrow.yaml
```

Change the `config/config.yaml` as required.

Start a container running the app with `docker compose watch`.

Watch it work using `docker compose logs -f sungather_evo`.

If you enabled the log file in your config.yaml using `tail -f
logs/SunGather.log` will also work. The log file will not contain stack traces
and output from the console export.  On the upside `tail` will not terminate due
to container restart. You can of course use both.

Now when you change code you can watch `docker compose` recognize the changed
file and restart the container. Any changes to code in the `SunGather`
directory, the `config/config.yaml` or the `registers/registers-sungrow.yaml`
will cause the container to restart.  Changing `requirements.txt` will trigger
a rebuild of the image before a restart of the container.

**Good luck and have fun!!**



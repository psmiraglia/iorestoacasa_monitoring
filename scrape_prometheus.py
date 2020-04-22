import urllib.request
import json
import time
import os
import logging

HOSTS_FILE = "/hosts.json"
SLEEP_TIME = int(os.getenv('SLEEP_TIME', '5'))

PROMETHEUS_SCHEME = os.getenv('PROMETHEUS_SCHEME', 'http')
PROMETHEUS_HOST = os.getenv('PROMETHEUS_HOST', 'prometheus')
PROMETHEUS_PORT = int(os.getenv('PROMETHEUS_PORT', '9090'))


LOG = logging.getLogger('scraper')
LOG.setLevel(logging.DEBUG)

fmt = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname).4s] %(message)s')
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
ch.setFormatter(fmt)
LOG.addHandler(ch)


def load_prometheus_query(query):
    LOG.info("Querying %s" % query)
    req = urllib.request.Request(url=query)
    with urllib.request.urlopen(req) as f:
        return json.loads(f.read().decode('utf-8'))

def clean_trailing_slash(url):
    if url[-1] == '/':
        return url[:-1]
    return url

def prometheus_query_url(query):
    return ("%s://%s:%s/api/v1/query?query=%s"
            % (PROMETHEUS_SCHEME, PROMETHEUS_HOST, PROMETHEUS_PORT, query))

def parse_jitsi_participant(server):
    d = {}
    d['name'] = clean_trailing_slash(server['metric']['jitsi_url'].replace('https://', ''))
    d['user_count'] = int(server['value'][1])
    d['by'] = server['metric']['jitsi_hosted_by']
    d['by_url'] = clean_trailing_slash(server['metric']['jitsi_hosted_by_url'])
    d['url'] = clean_trailing_slash(server['metric']['jitsi_url'])
    d['by_kind'] = server['metric']['jitsi_hosted_by_kind']
    d['software'] = server['metric']['software']
    d['available_bandwidth_mbps'] = server['metric']['available_bandwidth_mbps']
    d['core_count'] = server['metric']['core_count']
    return d

def parse_mm_data(server, is_static=True):
    d = {}
    d['url'] = clean_trailing_slash(server['metric']['url'])
    d['by'] = server['metric']['hosted_by']
    d['by_url'] = clean_trailing_slash(server['metric']['hosted_by_url'])
    d['by_kind'] = server['metric']['hosted_by_kind']
    d['software'] = server['metric']['software']
    d['available_bandwidth_mbps'] = server['metric']['available_bandwidth_mbps']
    d['core_count'] = server['metric']['core_count']

    if not is_static:
        d['cpu_usage'] = round(float(server['value'][1]), ndigits=2)
        d['name'] = clean_trailing_slash(server['metric']['url'].replace('https://', ''))
    else:
        d['name'] = clean_trailing_slash(server['metric']['jitsi_url'].replace('https://', ''))

    return d

def scrape_it():
    instances = {}
    credits = {
        'INSTITUTION': set(),
        'COMPANY': set(),
        'PERSON': set(),
        'ASSOCIATION': set(),
    }

    jitsi_required_labels = [
        'instance',
        'jitsi_hosted_by',
        'jitsi_hosted_by_url',
        'jitsi_url',
        'jitsi_hosted_by_kind',
        'software',
        'available_bandwidth_mbps',
        'core_count',
    ]

    mm_required_labels = [
        'instance',
        'url',
        'hosted_by',
        'hosted_by_url',
        'hosted_by_kind',
        'available_bandwidth_mbps',
        'core_count',
        'software',
    ]

    participants_data = load_prometheus_query(prometheus_query_url('jitsi_participants'))
    cpu_data = load_prometheus_query(prometheus_query_url('jitsi_cpu_usage'))
    static_mm_data = load_prometheus_query(prometheus_query_url('probe_success{software="MM"}'))
    mm_data = load_prometheus_query(prometheus_query_url('edumeet_cpu_usage'))
    mm_peers_data = load_prometheus_query(prometheus_query_url('edumeet_peers'))

    for server in participants_data['data']['result']:
        if not all(key in server['metric'] for key in jitsi_required_labels):
            continue
        if server['metric']['software'] == 'JITSI':
            d = parse_jitsi_participant(server)
            credits[d['by_kind']].add((d['by'], d['by_url']))
            instances[d['name']] = d
 
    for server in cpu_data['data']['result']:
        if not all(key in server['metric'] for key in jitsi_required_labels):
            continue
        if server['metric']['software'] == 'JITSI':
            name = clean_trailing_slash(server['metric']['jitsi_url'].replace('https://', ''))
            instances[name]['cpu_usage'] = round(float(server['value'][1]), ndigits=2)

    for server in static_mm_data['data']['result']:
        if not all(key in server['metric'] for key in mm_required_labels):
            continue
        if server['metric'].get('software') == 'MM' and server['value'][1] == '1':
            d = parse_mm_data(server)
            credits[d['by_kind']].add((d['by'], d['by_url']))
            instances[d['name']] = d

    for server in mm_data['data']['result']:
        if not all(key in server['metric'] for key in mm_required_labels):
            continue
        if server['metric'].get('software') == 'MM':
            d = parse_mm_data(server, False)
            credits[d['by_kind']].add((d['by'], d['by_url']))
            instances[d['name']] = d

    for server in mm_peers_data['data']['result']:
        if not all(key in server['metric'] for key in mm_required_labels):
            continue
        if server['metric']['software'] == 'MM':
            name = clean_trailing_slash(server['metric']['url'].replace('https://', ''))
            instances[name]['user_count'] = int(server['value'][1])


    new_credits = {}
    for key, item in credits.items():
        new_credits[key] = list(item)

    result = {
        'instances': list(instances.values()),
        'credits': new_credits,
    }

    with open(HOSTS_FILE, 'w') as f:
        f.write(json.dumps(result, indent=2))


if __name__ == '__main__':
    while True:
        scrape_it()
        LOG.info('Next scraping in %s seconds' % SLEEP_TIME)
        time.sleep(SLEEP_TIME)

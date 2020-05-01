__author__ = 'Dmitry Ustalov'

from collections import OrderedDict
from datetime import date, datetime, timedelta
from ipaddress import ip_address
from typing import Dict

import aiohttp_jinja2
import monetdblite
from aiohttp import web

from balcone import __version__
from balcone.core import VALID_SERVICE, Balcone


class WebBalcone:
    def __init__(self, balcone: Balcone):
        self.balcone = balcone

    @aiohttp_jinja2.template('root.html')
    async def root(self, _: web.Request):
        today = datetime.utcnow().date()

        services = self.balcone.dao.tables()

        dashboard = []

        for service in services:
            unique = self.balcone.unique(service, today, today)

            dashboard.append((service, unique.elements[0].count if unique.elements else 0))

        dashboard.sort(key=lambda service_count: (-service_count[1], service_count[0]))

        return {
            'version': __version__,
            'current_page': 'root',
            'services': services,
            'dashboard': dashboard
        }

    async def services(self, request: web.Request):
        raise web.HTTPFound(request.app.router['root'].url_for())

    @aiohttp_jinja2.template('service.html')
    async def service(self, request: web.Request):
        services = self.balcone.dao.tables()
        service = request.match_info.get('service', None)

        if not self.balcone.check_service(service):
            raise web.HTTPNotFound(text=f'No such service: {service}')

        stop = datetime.utcnow().date()
        start = stop - timedelta(days=7 - 1)

        queries = {
            'visits': self.balcone.visits(service, start, stop),
            'unique': self.balcone.unique(service, start, stop)
        }

        overview: Dict[date, Dict[str, int]] = OrderedDict()

        for query, result in queries.items():
            for element in result.elements:
                if element.date not in overview:
                    overview[element.date] = {}

                overview[element.date][query] = element.count

        time = self.balcone.time(service, start, stop)

        paths = self.balcone.uri(service, start, stop, limit=self.balcone.top_limit)

        browsers = self.balcone.browser(service, start, stop, limit=self.balcone.top_limit)

        return {
            'version': __version__,
            'services': services,
            'current_page': 'service',
            'current_service': service,
            'overview': overview,
            'time': time,
            'paths': paths,
            'browsers': browsers
        }

    async def query(self, request: web.Request):
        service, command = request.match_info['service'], request.match_info['query']

        if not self.balcone.check_service(service):
            raise web.HTTPNotFound(text=f'No such service: {service}')

        stop = datetime.utcnow().date()
        start = stop - timedelta(days=30 - 1)

        parameter = request.query.get('parameter', None)

        response = self.balcone.handle_command(service, command, parameter, start, stop)

        return web.json_response(response, dumps=self.balcone.json_dumps)

    @aiohttp_jinja2.template('sql.html')
    async def sql(self, request: web.Request):
        data = await request.post()
        sql, result, error = str(data.get('sql', 'SELECT 1, 2, 3;')), [], ''

        if sql:
            try:
                result = self.balcone.dao.run(sql)
            except monetdblite.exceptions.DatabaseError as e:
                error = str(e)

        services = self.balcone.dao.tables()

        return {
            'version': __version__,
            'current_page': 'sql',
            'title': 'SQL Console',
            'services': services,
            'sql': sql,
            'result': result,
            'error': error
        }

    @aiohttp_jinja2.template('nginx.html')
    async def nginx(self, request: web.Request):
        services = self.balcone.dao.tables()

        print(request.query)

        service = request.query.get('service')

        if not service:
            service = 'example'

        ip = request.query.get('ip')

        if not ip:
            ip = '127.0.0.1'

        error = []

        if not self.balcone.check_service(service, should_exist=False):
            error.append(f'Invalid service name: {self.balcone.json_dumps(service)}, '
                         f'must match /{VALID_SERVICE.pattern}/')

        try:
            ip_address(ip)
        except ValueError:
            error.append(f'Invalid Balcone IP address: {self.balcone.json_dumps(ip)}')

        return {
            'version': __version__,
            'current_page': 'nginx',
            'title': 'nginx Configuration',
            'services': services,
            'service': service,
            'ip': ip,
            'error': error
        }
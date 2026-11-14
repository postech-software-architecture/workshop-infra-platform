"""Replay a service DLQ with publisher confirms and ACK only after confirmed publish.
Run deliberately with a broker administrator account. Does not print message bodies or credentials.
"""
import argparse
import os
import json
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('service', choices=['os-service', 'billing-service', 'execucao-service'])
    parser.add_argument('--limit', type=int, default=1)
    parser.add_argument('--new-message-id', action='store_true', help='Only for deliberate reconciliation of a previously committed/ignored event; business identities remain unchanged.')
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error('limit must be between 1 and 100')
    import pika
    connection = pika.BlockingConnection(pika.URLParameters(os.environ['BROKER_ADMIN_URL']))
    try:
        channel = connection.channel()
        channel.confirm_delivery()
        count = 0
        for _ in range(args.limit):
            method, props, body = channel.basic_get(args.service + '.dlq', auto_ack=False)
            if method is None:
                break
            headers = dict(props.headers or {})
            headers['retry-count'] = 0
            if args.new_message_id:
                event = json.loads(body)
                event['causationId'] = event['messageId']
                event['messageId'] = str(uuid.uuid4())
                body = json.dumps(event).encode()
            published = pika.BasicProperties(content_type='application/json', delivery_mode=2, headers=headers,
                                             correlation_id=props.correlation_id)
            channel.basic_publish(exchange=args.service + '.retry', routing_key='retry',
                                  body=body, properties=published, mandatory=True)
            channel.basic_ack(method.delivery_tag)
            count += 1
        print(json.dumps({'service': args.service, 'redriven': count}))
    finally:
        connection.close()


if __name__ == '__main__':
    main()

import redis, time

pool = redis.ConnectionPool(host='localhost', port="6379", decode_responses=True)

r1 = redis.Redis(connection_pool=pool)
r1.set('AAA', 'AAA')
time.sleep(5)
q = r1.pipeline()
q.set('AAA', 'AAA1')
q.set('AAA1', 'AAA1')
q.set('AAA2', 'AAA2')
q.set('AAA3', 'AAA3')
q.execute()

r2 = redis.Redis(connection_pool=pool)
r2.set('BBB', 'BBB')
print(r1.get('AAA'))
print(r2.get('BBB'))

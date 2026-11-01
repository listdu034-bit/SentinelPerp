-- Acceptance fixtures: run ONLY against an empty, disposable test database.
-- The live integration suite expects exactly these counts; never use production.
INSERT INTO candles(time,symbol,receipt_timestamp,interval,open,high,low,close,volume)
SELECT date_trunc('minute',now())-(120-i)*interval '1 minute','BTC-USDT-SWAP',now(),'1m',100+i,102+i,99+i,101+i,10 FROM generate_series(1,120) AS i;
INSERT INTO trades(time,symbol,receipt_timestamp,trade_id,price,quantity,side)
SELECT now()-i*interval '1 second','BTC-USDT-SWAP',now(),i::text,100,1,'buy' FROM generate_series(1,120) AS i;
INSERT INTO quality_logs(time,event_id,data_type,symbol,issue_type,severity,details)
SELECT now()-i*interval '1 minute',md5('console-acceptance-'||i)::uuid,'trade','BTC-USDT-SWAP','gap',CASE WHEN i<=20 THEN 'warning' ELSE 'error' END,'{"acceptance":true}'::jsonb FROM generate_series(1,25) AS i;
CALL refresh_continuous_aggregate('candles_5m',now()-interval '3 days',now()+interval '2 days');
CALL refresh_continuous_aggregate('candles_1h',now()-interval '3 days',now()+interval '2 days');
CALL refresh_continuous_aggregate('candles_1d',now()-interval '3 days',now()+interval '2 days');

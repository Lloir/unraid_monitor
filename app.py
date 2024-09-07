import psutil
from flask import Flask, jsonify, render_template, request
import sqlite3
import os
import time
import json

app = Flask(__name__)

DB_PATH = '/app/cpu_memory_usage.db'  # Path to the SQLite database

# Ensure the SQLite DB and table exist
def init_db():
    if not os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE usage (
                timestamp INTEGER,
                cpu_usage TEXT,
                memory_usage REAL,
                network_rx REAL,
                network_tx REAL
            )
        ''')
        conn.commit()
        conn.close()

init_db()

# Helper function to store data in the database
def store_usage_data(cpu_usage, memory_usage, network_rx, network_tx):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO usage (timestamp, cpu_usage, memory_usage, network_rx, network_tx)
        VALUES (?, ?, ?, ?, ?)
    ''', (int(time.time()), json.dumps(cpu_usage), memory_usage, network_rx, network_tx))
    conn.commit()
    conn.close()

# Helper function to fetch all-time usage data from the database
def get_all_time_usage():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM usage')
    rows = c.fetchall()
    conn.close()

    # Prepare aggregates for all-time data
    cpu_aggregate = []
    memory_aggregate = 0
    network_rx_aggregate = 0
    network_tx_aggregate = 0

    total_entries = len(rows)

    # Accumulate CPU data per core across all entries
    for row in rows:
        timestamp, cpu_usage, memory_usage, network_rx, network_tx = row
        cpu_usage = json.loads(cpu_usage)

        if not cpu_aggregate:
            cpu_aggregate = [0] * len(cpu_usage)

        for i in range(len(cpu_usage)):
            cpu_aggregate[i] += cpu_usage[i]

        memory_aggregate += memory_usage
        network_rx_aggregate += network_rx
        network_tx_aggregate += network_tx

    # Compute average CPU usage per core
    if total_entries > 0:
        cpu_aggregate = [round(cpu / total_entries, 2) for cpu in cpu_aggregate]
        memory_aggregate = round(memory_aggregate / total_entries, 2)
    
    return {
        'cpu_per_core': cpu_aggregate,
        'memory': memory_aggregate,
        'network': {
            'rx': round(network_rx_aggregate, 2),
            'tx': round(network_tx_aggregate, 2)
        }
    }

# API to get real-time and historical data
@app.route('/api/data', methods=['GET'])
def get_data():
    timeframe = request.args.get('timeframe', 'current')

    if timeframe == 'all':
        # Fetch all-time data from the database
        all_time_data = get_all_time_usage()
        return jsonify(all_time_data)
    else:
        # Get real-time CPU, Memory, and Network usage
        cpu_per_core = psutil.cpu_percent(interval=1, percpu=True)
        memory = psutil.virtual_memory()
        net_io = psutil.net_io_counters()

        memory_used_percent = memory.percent
        network_rx = net_io.bytes_recv / (1024 ** 2)  # Convert bytes to MiB
        network_tx = net_io.bytes_sent / (1024 ** 2)  # Convert bytes to MiB

        # Store the data for persistence
        store_usage_data(cpu_per_core, memory_used_percent, network_rx, network_tx)

        result = {
            'cpu_per_core': cpu_per_core,
            'memory': memory_used_percent,
            'network': {
                'rx': network_rx,
                'tx': network_tx
            }
        }
        return jsonify(result)

# Serve the index.html page
@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

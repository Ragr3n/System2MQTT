import psutil
# Get all disk partitions
partitions = psutil.disk_partitions()
for partition in partitions:
    print(f"{partition.mountpoint}: {partition.device}")
    usage = psutil.disk_usage(partition.mountpoint)
    print(f"  Usage: {usage.percent}%")


disk = psutil.disk_usage('/')
print(f"Disk Usage for '/': {disk.percent}%")
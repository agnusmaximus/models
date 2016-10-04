import sys

hosts='\t'.join(sys.argv[2:]).split()
workers=hosts[:-1]
pss=hosts[-1]

if sys.argv[1] == "workers":
    print(",".join([x+":1234" for x in workers]))
else:
    print(pss+":1234")

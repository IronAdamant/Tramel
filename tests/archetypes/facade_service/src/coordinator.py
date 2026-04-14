from src.workers.worker_1 import task_1
from src.workers.worker_2 import task_2
from src.workers.worker_3 import task_3
from src.workers.worker_4 import task_4
from src.workers.worker_5 import task_5
from src.workers.worker_6 import task_6
from src.workers.worker_7 import task_7
from src.workers.worker_8 import task_8
from src.workers.worker_9 import task_9
from src.workers.worker_10 import task_10
from src.workers.worker_11 import task_11
from src.workers.worker_12 import task_12

def orchestrate():
    return sum([
        task_1(), task_2(), task_3(), task_4(),
        task_5(), task_6(), task_7(), task_8(),
        task_9(), task_10(), task_11(), task_12(),
    ])

import os
import sys
import yaml
import time
from copy import deepcopy
import multiprocessing as mp
import subprocess

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import global_control as gc

is_debug = False

#-------------------------------- default config ------------------------------

default_config = {
    'array_size': 64,
    "num_mac": 64,
    "bandwidth": 1024,
    "num_vcs": 4,
    "vc_buf_size": 2,
}

#------------------------------ helper functions ----------------------------

def generate_benchmark(args):
    """Generate default benchmark, change model name respectively
    Returns: save_path, model_name
    """
    model_name = f"gpt2-xl_m{args['num_mac']}_v{args['num_vcs']}_bs{args['vc_buf_size']}"

    layer2core = {
        0: 3*32,
        1: 1*32,
        2: 4*32,
        3: 4*32,
    }
    benchmark = [{f"gpt2-xl_layer{i + 1}": layer2core[i % 4]} for i in range(16 if not is_debug else 1)]
    benchmark = {model_name: benchmark}

    save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks", model_name)
    if not os.path.exists(save_dir):
        os.mkdir(save_dir)

    save_path = os.path.join(save_dir, "model.yaml")
    with open(save_path, "w") as f:
        yaml.dump(benchmark, f)
    
    return save_path, model_name


def generate_testcase():
    """Generate list of testcases
    """
    testcase_list = []
    if is_debug:
        testcase_list.append(default_config)

    else:
        # mac number
        for num_mac in [4, 8, 16, 32, 64, 128, 256]:
            config = deepcopy(default_config)
            config['num_mac'] = num_mac
            testcase_list.append(config)
        
        # bandwidth
        for bandwidth in [256, 512, 1024, 2048, 4096]:
            config = deepcopy(default_config)
            config['bandwidth'] = bandwidth
            testcase_list.append(config)
        
        # router design
        for total_buffer in [2, 4, 8, 16]:
            for num_vcs in [1, 2, 4, 8]:
                if num_vcs > total_buffer:
                    break
                vc_buf_size = total_buffer // num_vcs
                config = deepcopy(default_config)
                config['num_vcs'] = num_vcs
                config['vc_buf_size'] = vc_buf_size
                testcase_list.append(config)

    return testcase_list


def adjust_mac(num):
    """Adjust arch config yaml number of mac
    """
    assert num >= 2
    arch_path = os.path.join(gc.focus_root, "database", "arch", "cerebras_like.yaml")
    with open(arch_path, 'r') as f:
        arch_config = yaml.load(f, Loader=yaml.FullLoader)
    arch_config['architecture']['subtree'][0]['subtree'][0]['subtree'][0]['local'][-1]['name'] = f"LMAC[0..{num-1}]"
    with open(arch_path, 'w') as f:
        yaml.dump(arch_config, f)

#----------------------------- run single task -----------------------------------

def run_single_task(args, timeout=300):
    benchmark_path, model_name = generate_benchmark(args)
    adjust_mac(args['num_mac'])

    focus_path = os.path.join(gc.focus_root, "focus.py")
    focus_mode = "teds"
    array_size = args['array_size']
    flit_size = "-".join([str(args['bandwidth']) for _ in range(3)])
    command = f"python {focus_path} -bm {benchmark_path} -d {array_size} -b 1 \
                -fr {flit_size} {focus_mode}"
    if is_debug:
        command += " -debug"

    if is_debug:
        sp = subprocess.Popen(command, shell=True, start_new_session=True)
    else:
        sp = subprocess.Popen(command, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                shell=True, start_new_session=True)

    for _ in range(timeout):
        time.sleep(1)
        taskname = f"{model_name}_b1w{args['bandwidth']}_{array_size}x{array_size}"
        out_log_path = os.path.join(gc.simulator_root, taskname, "out.log")
        if os.path.exists(out_log_path):
            os.system(f"cp {out_log_path} {os.path.dirname(benchmark_path)}")
            return True

    print(f"Timeout when running task: {args}")
    return False


if __name__ == '__main__':
    is_debug = True
    run_single_task(default_config)
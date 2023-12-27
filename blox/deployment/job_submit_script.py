import os
import sys
import json
import grpc


sys.path.append(os.path.join(os.path.dirname(__file__), "./grpc_stubs"))
import grpc_stubs.rm_pb2 as rm_pb2
import grpc_stubs.rm_pb2_grpc as rm_pb2_grpc


def submit_dummy_job(ipaddr: str):
    """
    Submits dummy job to resource manager
    Args:
        ipaddr: Resource manager ip address
    """

    job_dict = {
        "launch_method": "file",
        "launch_command": "python test_mnist_job.py",
        "container_location": "temp",
        "config_parser_name": "temp",  # if parsing a config get this
        # which params to read from the config
        "config_params_name": {"temp": 1, "name": 2},
        # essentially the command to launch hopefully a bash script
        # TODO: Need to be careful
        "jop-params": "bash run.sh bsize lr other params",
        # TODO: Refine this
        "params_to_track": ["per_iter_time", "attained_service"],
        "default_values": [0, 0],  # default values for params to track
        # "parsing_params" : [AVG, S\UM]
        "num_GPUs": 1,
        "simulation": False,
    }
    for i in range(int(sys.argv[1])):
        with grpc.insecure_channel(ipaddr, options=(('grpc.enable_http_proxy', 0),)) as channel:
            stub = rm_pb2_grpc.RMServerStub(channel)
            response = stub.AcceptJob(
                rm_pb2.JsonResponse(response=json.dumps(job_dict))
            )
            print(response.value)


if __name__ == "__main__":
    submit_dummy_job("localhost:50051")

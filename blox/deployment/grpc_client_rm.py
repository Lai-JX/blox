import os
import sys
import json
import grpc
import logging
from typing import List
from concurrent import futures

sys.path.append(os.path.join((__file__), "./grpc_stubs"))
import nm_pb2
import nm_pb2_grpc

import rm_pb2

import simulator_pb2
import simulator_pb2_grpc


class ResourceManagerComm(object):
    """
    Resource Manager communication class
    """

    def __init__(self, node_manager_port) -> None:
        self.rpc_port = node_manager_port
        return None

    def launch_job(
        self,
        job_id: int,
        job_description: dict,
        local_gpu_ids: List[int],
        ipaddr_list: List[str],
    ) -> None:
        """
        Notify respesctive node managers to launch jobs
        Args:
            job_description: Job description from the job ID dictionary
            gpu_ids: Number of GPUS to launch
            ipaddr : list of IP address to contact node manager
        Returns:
            None
        """
        if job_description["simulation"] == False:
            for ipaddr, lgid in zip(ipaddr_list, local_gpu_ids):
                ipaddr = f"{ipaddr}:{self.rpc_port}"
                launch_dict = dict()
                launch_dict["job_id"] = job_id
                launch_dict["local_GPU_ID"] = lgid
                if "launch_command" not in job_description:
                    raise Exception("Missing Launch Command")
                launch_dict["launch_command"] = job_description["launch_command"]
                if "suspended" in job_description:
                    launch_dict["should_resume"] = job_description["suspended"]
                else:
                    launch_dict["should_resume"] = "0"
                launch_request = rm_pb2.JsonResponse()
                launch_request.response = json.dumps(launch_dict)
                with grpc.insecure_channel(ipaddr, options=(('grpc.enable_http_proxy', 0),)) as channel:
                    stub = nm_pb2_grpc.NMServerStub(channel)
                    response = stub.LaunchJob(launch_request)
                print(
                    f"Launched Job {job_id}, response {response}, request {launch_dict}"
                )

            return None
        elif job_description["simulation"] == True:
            # TODO: Add time for checkpoint and restore
            return None

    def terminate_jobs(
        self,
        job_id_list: List[int],
        ipaddr_list: List[str],
        terminate_simulation: List[bool],
    ) -> None:
        """
        Given a list of Job_ID's and their corresponding ip addresses.
        Terminate these jobs.
        Args:
            job_id: list of job ids to terminate
            ipaddr: list of corresponding ip addresses
            terminate_simulation : whether job is simulation or not
        Returns:
            None
        """
        # TODO: Multithread this
        for job_id, ipaddr, simulation in zip(
            job_id_list, ipaddr_list, terminate_simulation
        ):
            if not terminate_simulation:
                # only launch termination if false
                ipaddr = f"{ipaddr}:{self.rpc_port}"
                terminate_request = rm_pb2.JsonResponse()
                terminate_request.response = json.dumps({"Job_ID": job_id})
                # TODO: Add simulator
                with grpc.insecure_channel(ipaddr, options=(('grpc.enable_http_proxy', 0),)) as channel:
                    stub = nm_pb2_grpc.NMServerStub(channel)
                    response = stub.TerminateJob(terminate_request)
        return None

    def get_metrics(
        self,
        job_id_list: List[int],
        ipaddr_list: List[str],
        if_simulation: List[bool],
        round_duration: int,
        active_job_dict: dict,
    ) -> dict:
        """
        Given a job ID list fetch metrics from all the node managers
        job_id_list : List of Job ID's
        ipaddr_list : List of corresponding Job ID's
        if_simulation: List of boolean telling if the job is simulation or not
        round_duration: Represents the round duration
        active_job_dict: Active jobs dictionary
        #CAUTION: In case simulation we modify some of the parameters in place.
        """
        # TODO: Multi-thread this
        metric_data_dict = dict()
        for job_id, ipaddr, if_sim in zip(job_id_list, ipaddr_list, if_simulation):
            job_exit = False
            if not if_sim:
                ipaddr = f"{ipaddr}:{self.rpc_port}"
                metric_request = rm_pb2.JsonResponse()
                metric_request.response = json.dumps({"Job_ID": job_id})
                with grpc.insecure_channel(ipaddr, options=(('grpc.enable_http_proxy', 0),)) as channel:
                    stub = nm_pb2_grpc.NMServerStub(channel)
                    response = stub.GetMetrics(metric_request)
                metric_data = json.loads(response.response)
                metric_data_dict[job_id] = metric_data
            else:
                # this is a simulation
                # profile scaling by number of GPUs
                total_gpus = [5, 3, 1.4, 1.2, 1.1, 1.0, 1.0, 1.0, 1.0]
                self.optimus_scale_by_gpus = {
                    "1.0": total_gpus[0],
                    "2.0": total_gpus[1],
                    "3.0": total_gpus[2],
                    "4.0": total_gpus[3],
                    "5.0": total_gpus[4],
                    "6.0": total_gpus[5],
                    "7.0": total_gpus[6],
                    "8.0": total_gpus[7],
                    "9.0": total_gpus[8],
                }
                if active_job_dict[job_id]["previously_launched"] == False:
                    active_job_dict[job_id]["job_launched_first_time"] = True
                if active_job_dict[job_id]["previously_launched"] == True:
                    active_job_dict[job_id]["job_launched_first_time"] = False

                active_job_dict[job_id]["previously_launched"] = True

                total_iterations_in_round = (
                    round_duration / active_job_dict[job_id]["job_iteration_time"]
                )
                attained_service = (
                    active_job_dict[job_id]["tracked_metrics"]["attained_service"]
                    + round_duration
                )

                per_iteration_time = active_job_dict[job_id]["job_iteration_time"]

                total_iteration_achieved = (
                    total_iterations_in_round
                    + active_job_dict[job_id]["job_executed_iteration"]
                )
                if os.environ["sched_policy"] == "Optimus":
                    total_iteration_achieved = (
                        total_iterations_in_round
                        * self.optimus_scale_by_gpus[
                            active_job_dict[job_id]["total_gpus"]
                        ]
                        + active_job_dict[job_id]["job_executed_iteration"]
                    )
                if (
                    total_iteration_achieved
                    >= active_job_dict[job_id]["job_total_iteration"]
                ):
                    job_exit = True

                # CAUTION: In place update
                # TODO: Clean this part of update
                active_job_dict[job_id][
                    "job_executed_iteration"
                ] = total_iteration_achieved

                if job_exit == True:
                    metric_data_dict[job_id] = {
                        "attained_service": attained_service,
                        "per_iter_time": per_iteration_time,
                        "job_exit": True,
                    }
                if not job_exit:
                    metric_data_dict[job_id] = {
                        "attained_service": attained_service,
                        "per_iter_time": per_iteration_time,
                    }

        return metric_data_dict

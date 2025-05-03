import json
from enum import Enum

import boto3
from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.utils import is_intent_name, is_request_type
from ask_sdk_model import Response

AWS_REGION = "eu-west-2"
INSTANCE_SIZE = "2xlarge"
LAUNCH_TEMPLATE_ID = "lt-01ee014372da8099d"

# Instance types
class InstanceType(Enum):
    G4DN = "g4dn"
    G4AD = "g4ad"
    G5 = "g5"


# Instance status enum
class InstanceStatus(Enum):
    LAUNCHED = "LAUNCHED"
    TERMINATED = "TERMINATED"
    REBOOTED = "REBOOTED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    INSTANCE_FOUND = "INSTANCE_FOUND"
    INSTANCE_NOT_FOUND = "INSTANCE_NOT_FOUND"
    AMI_NOT_FOUND = "AMI_NOT_FOUND"
    EXCEPTION = "EXCEPTION"

ec2 = boto3.client("ec2", region_name=AWS_REGION)

sb = SkillBuilder()


class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        speech_text = "This is Cloud Rig."
        return (
            handler_input.response_builder.speak(speech_text)
            .set_should_end_session(False)
            .response
        )


class LaunchInstanceIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("LaunchInstance")(handler_input)

    def handle(self, handler_input):
        instance_type = get_instance_type(
            handler_input.request_envelope.request.intent.slots[
                "InstanceType"
            ].value.lower()
        )
        # get enum for instance type string
        launch_status = launch_instance(instance_type)

        if launch_status == InstanceStatus.SUCCESS:
            return (
                handler_input.response_builder.speak(
                    f"<speak>Instance of type <say-as interpret-as='spell-out'>{instance_type.value}</say-as> launched.</speak>"
                )
                .set_should_end_session(True)
                .response
            )
        elif launch_status == InstanceStatus.FAILED:
            return handler_input.response_builder.speak(
                "Failed to launch gaming instance."
            ).response
        elif launch_status == InstanceStatus.INSTANCE_EXISTS:
            return (
                handler_input.response_builder.speak("Gaming instance already running.")
                .set_should_end_session(True)
                .response
            )
        elif launch_status == InstanceStatus.AMI_NOT_FOUND:
            return (
                handler_input.response_builder.speak("Gaming AMI not found.")
                .set_should_end_session(True)
                .response
            )
        elif launch_status == InstanceStatus.EXCEPTION:
            return (
                handler_input.response_builder.speak("An exception occurred, see logs.")
                .set_should_end_session(True)
                .response
            )


class TerminateInstanceIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("TerminateInstance")(handler_input)

    def handle(self, handler_input):
        confirmationStatus = (
            handler_input.request_envelope.request.intent.confirmationStatus
        )
        if confirmationStatus != "CONFIRMED":
            return handler_input.response_builder.speak(
                "Termination cancelled."
            ).response

        termination_status = terminate_instance(handler_input.request_envelope.request)

        if termination_status == InstanceStatus.TERMINATED:
            return (
                handler_input.response_builder.speak(
                    '<speak>Gaming instance terminated. <amazon:emotion name="disappointed" intensity="high">Game over.</amazon:emotion></speak>'
                )
                .set_should_end_session(True)
                .response
            )
        elif termination_status == InstanceStatus.INSTANCE_NOT_FOUND:
            return (
                handler_input.response_builder.speak(
                    "No gaming instance found to terminate."
                )
                .set_should_end_session(True)
                .response
            )
        elif termination_status == InstanceStatus.FAILED:
            return (
                handler_input.response_builder.speak(
                    "Failed to terminate gaming instance, see logs."
                )
                .set_should_end_session(True)
                .response
            )
        elif termination_status == InstanceStatus.EXCEPTION:
            return (
                handler_input.response_builder.speak("An exception occurred, see logs.")
                .set_should_end_session(True)
                .response
            )


class RebootInstanceIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("RebootInstance")(handler_input)

    def handle(self, handler_input):
        confirmationStatus = (
            handler_input.request_envelope.request.intent.confirmationStatus
        )
        if confirmationStatus != "CONFIRMED":
            return handler_input.response_builder.speak("Reboot cancelled.").response

        instance_status = reboot_instance(handler_input.request_envelope.request)

        if instance_status == InstanceStatus.REBOOTED:
            return (
                handler_input.response_builder.speak(
                    "Gaming instance rebooted, game on!"
                )
                .set_should_end_session(True)
                .response
            )
        elif instance_status == InstanceStatus.INSTANCE_NOT_FOUND:
            return (
                handler_input.response_builder.speak(
                    "No gaming instance found to reboot."
                )
                .set_should_end_session(True)
                .response
            )
        elif instance_status == InstanceStatus.EXCEPTION:
            return (
                handler_input.response_builder.speak("An exception occurred, see logs.")
                .set_should_end_session(True)
                .response
            )


class IsInstanceRunningIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("IsInstanceRunning")(handler_input)

    def handle(self, handler_input):
        if is_instance_running():
            speech_text = "Instance detected."
        else:
            speech_text = "Instance not found."
        return handler_input.response_builder.speak(speech_text).response


class HelpIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        speech_text = (
            "<speak>"
            "You can ask me to launch a gaming instance with a recognised"
            "launch command and by specifying the instance type. For example, "
            "cloud rig, launch type"
            "<say-as interpret-as='spell-out'>g4ad</say-as>.</speak>"
        )
        return handler_input.response_builder.speak(speech_text).response


class CancelOrStopIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.CancelIntent")(handler_input) or is_intent_name(
            "AMAZON.StopIntent"
        )(handler_input)

    def handle(self, handler_input):
        speech_text = (
            "<speak>"
            '<amazon:emotion name="disappointed" intensity="high">Game over.</amazon:emotion>'
            "</speak>"
        )
        return (
            handler_input.response_builder.speak(speech_text)
            .set_should_end_session(True)
            .response
        )


class SessionEndedRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        return handler_input.response_builder.response


def launch_instance(instance_type):
    if is_instance_running():
        return InstanceStatus.INSTANCE_FOUND

    images = ec2.describe_images(
        Filters=[{"Name": "tag:Name", "Values": ["gaming-rig"]}]
    )["Images"]
    if len(images) == 0:
        return InstanceStatus.AMI_NOT_FOUND

    ami_id = images[0]["ImageId"]
    params = {
        "ImageId": ami_id,
        "InstanceType": f"{instance_type.value}.{INSTANCE_SIZE}",
        "LaunchTemplate": {
            "LaunchTemplateId": LAUNCH_TEMPLATE_ID,
        },
        "MinCount": 1,
        "MaxCount": 1,
    }
    print(f"Params: {params}")
    try:
        data = ec2.run_instances(**params)
        if len(data["Instances"]) == 0:
            return InstanceStatus.FAILED
        print(f"Instance {data["Instances"][0]["InstanceId"]} launched")
        return InstanceStatus.LAUNCHED
    except Exception as error:
        print(str(error))
        return InstanceStatus.EXCEPTION


def terminate_instance(event):
    instance = get_running_instance()
    if len(instance) == 0:
        return InstanceStatus.INSTANCE_NOT_FOUND

    instance_id = instance[0]["Instances"][0]["InstanceId"]
    try:
        ec2.terminate_instances(InstanceIds=[instance_id])
        print(f"Instance {instance_id} terminated")
        return InstanceStatus.TERMINATED
    except Exception as error:
        print(str(error))
        return InstanceStatus.EXCEPTION


def reboot_instance(event):
    instance = get_running_instance()
    if len(instance) == 0:
        return InstanceStatus.INSTANCE_NOT_FOUND

    instance_id = instance[0]["Instances"][0]["InstanceId"]
    try:
        ec2.reboot_instances(InstanceIds=[instance_id])
        print(f"Instance {instance_id} rebooted.")
        return InstanceStatus.REBOOTED
    except Exception as error:
        print(str(error))
        return InstanceStatus.EXCEPTION


# get enum value from string
def get_instance_type(instance_type):
    return InstanceType[instance_type.upper()]


# is string valid enum value
def is_valid_instance_type(instance_type):
    return instance_type in [e.value for e in InstanceType]

def get_running_instance():
    return ec2.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": ["gaming-rig"]},
            {"Name": "instance-state-name", "Values": ["running"]},
        ]
    )["Reservations"]


def is_instance_running(event=None):
    return len(get_running_instance()) > 0


sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(LaunchInstanceIntentHandler())
sb.add_request_handler(TerminateInstanceIntentHandler())
sb.add_request_handler(RebootInstanceIntentHandler())
sb.add_request_handler(IsInstanceRunningIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())

lambda_handler = sb.lambda_handler()

"""
This module provides functionality to manage AWS EC2 instances for cloud gaming using AWS Lambda.

Classes:
    InstanceType(Enum): Enum representing different types of EC2 instances.
    InstanceStatus(Enum): Enum representing various statuses of EC2 instances.

Functions:
    lambda_handler(event, context): Main entry point for the AWS Lambda function.
    on_launch(): Handles the LaunchRequest event.
    on_intent(event): Handles the IntentRequest event.
    on_session_ended(): Handles the SessionEndedRequest event.
    launch_instance(instance_type): Launches an EC2 instance of the specified type.
    terminate_instance(): Terminates the running EC2 instance.
    reboot_instance(): Reboots the running EC2 instance.
    get_instance_type(instance_type): Converts a string to an InstanceType enum.
    is_valid_instance_type(instance_type): Checks if the given instance type is valid.
    get_running_instance(): Retrieves the currently running EC2 instance.
    is_instance_running(event=None): Checks if there is a running EC2 instance.
    build_response(output, should_end_session=False): Builds a plain text response for the Alexa skill.
    build_ssml_response(output, should_end_session=False): Builds an SSML response for the Alexa skill.
"""

from enum import Enum
import boto3
import logging

logging.basicConfig(level=logging.INFO)

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
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    request_type = event["request"]["type"]
    if request_type == "LaunchRequest":
        return on_launch()
    elif request_type == "IntentRequest":
        return on_intent(event)
    elif request_type == "SessionEndedRequest":
        return on_session_ended()


def on_launch():
    return build_response("This is Cloud Rig.", False)


def on_intent(event):
    intent_name = event["request"]["intent"]["name"]
    logger.info("Handing intent: {intent_name}")
    # LaunchInstance intent
    if intent_name == "LaunchInstance":
        instance_type = get_instance_type(
            event["request"]["intent"]["slots"]["InstanceType"]["value"].lower()
        )
        launch_status = launch_instance(instance_type)
        if launch_status == InstanceStatus.LAUNCHED:
            return build_ssml_response(
                f"<speak>Instance of type <say-as interpret-as='spell-out'>{instance_type.value}</say-as> launched.</speak>",
                True,
            )
        elif launch_status == InstanceStatus.FAILED:
            return build_response("Failed to launch gaming instance.", True)
        elif launch_status == InstanceStatus.INSTANCE_FOUND:
            return build_response("Gaming instance already running.", True)
        elif launch_status == InstanceStatus.AMI_NOT_FOUND:
            return build_response("Gaming AMI not found.", True)
        elif launch_status == InstanceStatus.EXCEPTION:
            return build_response("An exception occurred, see logs.", True)
    # Terminate instance intent
    elif intent_name == "TerminateInstance":
        confirmation_status = event["request"]["intent"]["confirmationStatus"]
        if confirmation_status != "CONFIRMED":
            return build_response("Termination cancelled.")
        termination_status = terminate_instance()
        if termination_status == InstanceStatus.TERMINATED:
            return build_ssml_response(
                '<speak>Gaming instance terminated. <amazon:emotion name="disappointed" intensity="high">Game over.</amazon:emotion></speak>',
                True,
            )
        elif termination_status == InstanceStatus.INSTANCE_NOT_FOUND:
            return build_response("No gaming instance found to terminate.", True)
        elif termination_status == InstanceStatus.FAILED:
            return build_response(
                "Failed to terminate gaming instance, see logs.", True
            )
        elif termination_status == InstanceStatus.EXCEPTION:
            return build_response("An exception occurred, see logs.", True)
    # Reboot instance intent
    elif intent_name == "RebootInstance":
        confirmation_status = event["request"]["intent"]["confirmationStatus"]
        if confirmation_status != "CONFIRMED":
            return build_response("Reboot cancelled.")
        instance_status = reboot_instance()
        if instance_status == InstanceStatus.REBOOTED:
            return build_response("Gaming instance rebooted, game on!", True)
        elif instance_status == InstanceStatus.INSTANCE_NOT_FOUND:
            return build_response("No gaming instance found to reboot.", True)
        elif instance_status == InstanceStatus.EXCEPTION:
            return build_response("An exception occurred, see logs.", True)
    # IsInstanceRunning intent
    elif intent_name == "IsInstanceRunning":
        if is_instance_running():
            return build_response("Instance detected.")
        else:
            return build_response("Instance not found.")
    # Help intent
    elif intent_name == "AMAZON.HelpIntent":
        return build_ssml_response(
            "<speak>You can ask me to launch a gaming instance with a recognised launch command and by specifying the instance type. For example, cloud rig, launch type <say-as interpret-as='spell-out'>g4ad</say-as>.</speak>"
        )
    # Stop and cancel intents
    elif intent_name == "AMAZON.CancelIntent" or intent_name == "AMAZON.StopIntent":
        return on_session_ended()
    else:
        return build_response("Sorry, I don't know that one.")


def on_session_ended():
    return build_ssml_response(
        '<speak><amazon:emotion name="disappointed" intensity="high">Game over.</amazon:emotion></speak>',
        True,
    )


def launch_instance(instance_type):
    """
    Launches an EC2 instance of the specified type.

    Args:
        instance_type (InstanceType): The type of instance to launch.

    Returns:
        InstanceStatus: The status of the instance launch operation.

    Possible return values:
        - InstanceStatus.INSTANCE_FOUND: If an instance is already running.
        - InstanceStatus.AMI_NOT_FOUND: If no AMI with the tag "gaming-rig" is found.
        - InstanceStatus.FAILED: If the instance launch failed.
        - InstanceStatus.LAUNCHED: If the instance was successfully launched.
        - InstanceStatus.EXCEPTION: If an exception occurred during the launch process.
    """
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
    logger.info("Params: %s", params)
    try:
        data = ec2.run_instances(**params)
        if len(data["Instances"]) == 0:
            return InstanceStatus.FAILED
        logger.info("Instance %s launched", {data["Instances"][0]["InstanceId"]})
        return InstanceStatus.LAUNCHED
    except Exception as error:
        logger.exception(error)
        return InstanceStatus.EXCEPTION


def terminate_instance():
    instance = get_running_instance()
    if len(instance) == 0:
        return InstanceStatus.INSTANCE_NOT_FOUND

    instance_id = instance[0]["Instances"][0]["InstanceId"]
    try:
        ec2.terminate_instances(InstanceIds=[instance_id])
        logger.info(f"Instance {instance_id} terminated")
        return InstanceStatus.TERMINATED
    except Exception as error:
        logger.exception(error)
        return InstanceStatus.EXCEPTION


def reboot_instance():
    instance = get_running_instance()
    if len(instance) == 0:
        return InstanceStatus.INSTANCE_NOT_FOUND

    instance_id = instance[0]["Instances"][0]["InstanceId"]
    try:
        ec2.reboot_instances(InstanceIds=[instance_id])
        logger.info(f"Instance {instance_id} rebooted.")
        return InstanceStatus.REBOOTED
    except Exception as error:
        logger.exception(error)
        return InstanceStatus.EXCEPTION


def get_instance_type(instance_type):
    return InstanceType[instance_type.upper()]


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


def build_response(output, should_end_session=False):
    return {
        "version": "1.0",
        "response": {
            "outputSpeech": {"type": "PlainText", "text": output},
            "shouldEndSession": should_end_session,
        },
    }


def build_ssml_response(output, should_end_session=False):
    return {
        "version": "1.0",
        "response": {
            "outputSpeech": {"type": "SSML", "ssml": output},
            "shouldEndSession": should_end_session,
        },
    }

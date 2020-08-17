#
#  Copyright 2019 The FATE Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
import copy

from pipeline.utils.logger import LOGGER


class Component(object):
    __instance = {}

    def __init__(self, *args, **kwargs):
        # print ("kwargs : ", kwargs)
        LOGGER.debug(f"kwargs: {kwargs}")
        if "name" in kwargs:
            self._component_name = kwargs["name"]
        self.__party_instance = {}
        self._algorithm_parameter_keywords = set(kwargs.keys())
        self._role_parameter_keywords = set()
        self._module_name = None
        self._algorithm_param = {}

    def __new__(cls, *args, **kwargs):
        if cls.__name__.lower() not in cls.__instance:
            cls.__instance[cls.__name__.lower()] = 0

        new_cls = object.__new__(cls)
        new_cls.set_name(cls.__instance[cls.__name__.lower()])
        cls.__instance[cls.__name__.lower()] += 1

        return new_cls

    def set_name(self, idx):
        self._component_name = self.__class__.__name__.lower() + "_" + str(idx)
        # print("enter set name func", self._component_name)
        LOGGER.debug(f"enter set name func {self._component_name}")

    def reset_name(self, name):
        self._component_name = name

    def get_party_instance(self, role="all", party_id=None) -> 'Component':
        if role not in ["all", "guest", "host", "arbiter"]:
            raise ValueError("Role should be one of guest/host/arbiter, if not set, default is all")

        if role == "all":
            if party_id is not None:
                raise ValueError("when role is all, party_id should not be set")

        if party_id is not None:
            if isinstance(party_id, list):
                for _id in party_id:
                    if not isinstance(_id, int) or _id <= 0:
                        raise ValueError("party id should be positive integer")
            elif not isinstance(party_id, int) or party_id <= 0:
                raise ValueError("party id should be positive integer")

        if role not in self.__party_instance:
            self.__party_instance[role] = {}
            self.__party_instance[role]["party"] = {}

        party_key = party_id

        if isinstance(party_id, list):
            party_key = "|".join(map(str, party_id))

        if party_key not in self.__party_instance[role]["party"]:
            self.__party_instance[role]["party"][party_key] = None

        if not self.__party_instance[role]["party"][party_key]:
            party_instance = copy.deepcopy(self)
            self._decrease_instance_count()

            self.__party_instance[role]["party"][party_key] = party_instance
            # print ("enter init")
            LOGGER.debug(f"enter init")

        return self.__party_instance[role]["party"][party_key]

    @classmethod
    def _decrease_instance_count(cls):
        cls.__instance[cls.__name__.lower()] -= 1
        # print ("decrease instance count")
        LOGGER.debug(f"decrease instance count")

    @property
    def name(self):
        return self._component_name

    @property
    def module(self):
        return self._module_name

    def algorithm_param(self, **kwargs):
        new_kwargs = copy.deepcopy(kwargs)
        for attr in self.__dict__:
            if attr in new_kwargs:
                setattr(self, attr, new_kwargs[attr])
                self._algorithm_param[attr] = new_kwargs[attr]
                del new_kwargs[attr]

        for attr in new_kwargs:
            # print ("key {}, value {} not use".format(attr, new_kwargs[attr]))
            LOGGER.warning(f"key {attr}, value {new_kwargs[attr]} not use")

        self._role_parameter_keywords |= set(kwargs.keys())

    def get_algorithm_param(self):
        return self._algorithm_param

    def get_algorithm_param_conf(self):
        """
        exclude_attr = ["_component_name", "__party_instance",
                        "_algorithm_parameter_keywords", "_role_parameter_keywords"]
        """

        algorithm_param_conf = {}
        for attr in self.__dict__:
            if attr.startswith("_"):
                continue

            if attr in self._role_parameter_keywords:
                continue

            if attr not in self._algorithm_parameter_keywords:
                continue

            algorithm_param_conf[attr] = getattr(self, attr)

        return algorithm_param_conf

    def recursive_construct_role_parameters_v1(self, params, partys=None, all_party_ids=None):
        ret_dict = {}
        for param, value in params.items():
            if not isinstance(value, dict) or len(value.keys()) == 1:
                if partys is None:
                    ret_dict[param] = [value] * len(all_party_ids)
                else:
                    ret_dict[param] = [PlaceHolder] * len(all_party_ids)
                    for party in partys:
                        ret_dict[param][all_party_ids.index(party)] = value
            else:
                attr = list(value.keys())[0]
                if hasattr(self, attr):
                    ret_dict[param] = self.recursive_construct_role_parameters_v1(value, partys, all_party_ids)
                else:
                    ret_dict[param] = [value]

        return ret_dict

    def flattern_role_parameters_v1(self, role_params):
        ret_dict = {}
        for param, value in role_params.items():
            new_value = []
            if not isinstance(value, dict) or len(value.keys()) == 1:
                for val in value:
                    if isinstance(val, PlaceHolder):
                        new_value.append(getattr(self, param))
                    else:
                        new_value.append(val)
                ret_dict[param] = new_value
            else:
                attr = list(value.keys())[0]
                if hasattr(self, attr):
                    ret_dict[param] = self.flattern_role_parameters_v1(value)
                else:
                    for val in value:
                        if isinstance(val, PlaceHolder):
                            new_value.append(getattr(self, param))
                        else:
                            new_value.append(val)
                    ret_dict[param] = new_value

        return ret_dict

    def get_role_param_conf(self, roles=None):
        role_param_conf = {}

        if not self.__party_instance:
            return role_param_conf

        for role in self.__party_instance:
            if role == "all":
                pass

            role_param_conf[role] = {}
            if None in self.__party_instance[role]["party"]:
                role_all_party_conf = self.__party_instance[role]["party"][None].get_algorithm_param()
                if "all" not in role_param_conf:
                    role_param_conf[role]["all"] = {}
                    role_param_conf[role]["all"][self._component_name] = role_all_party_conf

            valid_partyids = roles.get(role)
            for party_id in self.__party_instance[role]["party"]:
                if not party_id:
                    continue

                if isinstance(party_id, int):
                    party_key = str(valid_partyids.index(party_id))
                else:
                    party_list = list(map(int, party_id.split("|", -1)))
                    party_key = "|".join(map(str, [valid_partyids.index(party) for party in party_list]))

                party_inst = self.__party_instance[role]["party"][party_id]

                if party_key not in role_param_conf:
                    role_param_conf[role][party_key] = {}

                role_param_conf[role][party_key][self._component_name] = party_inst.get_algorithm_param()

        # print ("role_param_conf {}".format(role_param_conf))
        LOGGER.debug(f"role_param_conf {role_param_conf}")
        return role_param_conf

    @classmethod
    def erase_component_base_param(cls, **kwargs):
        new_kwargs = copy.deepcopy(kwargs)
        if "name" in new_kwargs:
            del new_kwargs["name"]

        return new_kwargs

    def get_config(self, *args, **kwargs):
        """need to implement"""

        roles = kwargs["roles"]

        algorithm_param_conf = self.get_algorithm_param_conf()
        role_param_conf = self.get_role_param_conf(roles)

        conf = {}
        if algorithm_param_conf:
            conf['algorithm_parameters'] = {self._component_name: algorithm_param_conf}

        if role_param_conf:
            conf["role_parameters"] = role_param_conf

        return conf

    def summary(self, *args):
        """need to implement"""
        pass


class PlaceHolder(object):
    pass

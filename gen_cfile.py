#!/usr/bin/env python
# -*- coding: utf-8 -*-

#This file is part of CanFestival, a library implementing CanOpen Stack. 
#
#Copyright (C): Edouard TISSERANT and Francis DUPIN
#
#See COPYING file for copyrights details.
#
#This library is free software; you can redistribute it and/or
#modify it under the terms of the GNU Lesser General Public
#License as published by the Free Software Foundation; either
#version 2.1 of the License, or (at your option) any later version.
#
#This library is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#Lesser General Public License for more details.
#
#You should have received a copy of the GNU Lesser General Public
#License along with this library; if not, write to the Free Software
#Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

from node import *
from types import *

import re, os

word_model = re.compile('([a-zA-Z_0-9]*)')
type_model = re.compile('([\_A-Z]*)([0-9]*)')
range_model = re.compile('([\_A-Z]*)([0-9]*)\[([\-0-9]*)-([\-0-9]*)\]')

categories = [("SDO_SVR", 0x1200, 0x127F), ("SDO_CLT", 0x1280, 0x12FF),
              ("PDO_RCV", 0x1400, 0x15FF), ("PDO_RCV_MAP", 0x1600, 0x17FF),
              ("PDO_TRS", 0x1800, 0x19FF), ("PDO_TRS_MAP", 0x1A00, 0x1BFF)]
index_categories = ["firstIndex", "lastIndex"]

generated_tag = """\n/* File generated by gen_cfile.py. Should not be modified. */\n"""

internal_types = {}
default_string_size = 10

#Verify that the name does not start with a digit
def UnDigitName(name):
    start_with_digit = re.compile(r'^(\d.*)')
    if start_with_digit.match(name):
        return start_with_digit.sub(r'_\1', name)
    return name


# Format a string for making a C++ variable
def FormatName(name):
    wordlist = [word for word in word_model.findall(name) if word != '']
    return "_".join(wordlist)

# Extract the informations from a given type name
def GetValidTypeInfos(typename, items=[]):
    if typename in internal_types:
        return internal_types[typename]
    else:
        result = type_model.match(typename)
        if result:
            values = result.groups()
            if values[0] == "UNSIGNED" and int(values[1]) in [i * 8 for i in xrange(1, 9)]:
                typeinfos = ("UNS%s"%values[1], None, "uint%s"%values[1], True)
            elif values[0] == "INTEGER" and int(values[1]) in [i * 8 for i in xrange(1, 9)]:
                typeinfos = ("INTEGER%s"%values[1], None, "int%s"%values[1], False)
            elif values[0] == "REAL" and int(values[1]) in (32, 64):
                typeinfos = ("%s%s"%(values[0], values[1]), None, "real%s"%values[1], False)
            elif values[0] in ["VISIBLE_STRING", "OCTET_STRING"]:
                size = default_string_size
                for item in items:
                    size = max(size, len(item))
                if values[1] != "":
                    size = max(size, int(values[1]))
                typeinfos = ("UNS8", size, "visible_string", False)
            elif values[0] == "DOMAIN":
                size = 0
                for item in items:
                    size = max(size, len(item))
                typeinfos = ("UNS8", size, "domain", False)
            elif values[0] == "BOOLEAN":
                typeinfos = ("UNS8", None, "boolean", False)
            else:
                raise ValueError, _("""!!! %s isn't a valid type for CanFestival.""")%typename
            if typeinfos[2] not in ["visible_string", "domain"]:
                internal_types[typename] = typeinfos
        else:
            raise ValueError, _("""!!! %s isn't a valid type for CanFestival.""")%typename
    return typeinfos

def ComputeValue(type, value):
    if type == "visible_string":
        return "\"%s\""%value, ""
    elif type == "domain":
        return "\"%s\""%''.join(["\\x%2.2x"%ord(char) for char in value]), ""
    elif type.startswith("real"):
        return "%f"%value, ""
    else:
        if value < 0:
            return "-0x%X"%abs(value), "\t/* %s */"%str(abs(value))
        else:
            return "0x%X"%value, "\t/* %s */"%str(value)

def WriteFile(filepath, content):
    cfile = open(filepath,"w")
    cfile.write(content)
    cfile.close()

def GetTypeName(Node, typenumber):
    typename = Node.GetTypeName(typenumber)
    if typename is None:
        raise ValueError, _("""!!! Datatype with value "0x%4.4X" isn't defined in CanFestival.""")%typenumber
    return typename

def GenerateFileContent(Node, headerfilepath, pointers_dict = {}):
    """
    pointers_dict = {(Idx,Sidx):"VariableName",...}
    """
    global type
    global internal_types
    global default_string_size
    
    texts = {}
    texts["maxPDOtransmit"] = 0
    texts["NodeName"] = Node.GetNodeName()
    texts["NodeID"] = Node.GetNodeID()
    texts["NodeType"] = Node.GetNodeType()
    texts["Description"] = Node.GetNodeDescription()
    texts["iam_a_slave"] = 0
    if (texts["NodeType"] == "slave"):
        texts["iam_a_slave"] = 1
    
    default_string_size = Node.GetDefaultStringSize()
    
    # Compiling lists of indexes
    rangelist = [idx for idx in Node.GetIndexes() if 0 <= idx <= 0x260]
    listIndex = [idx for idx in Node.GetIndexes() if 0x1000 <= idx <= 0xFFFF]
    communicationlist = [idx for idx in Node.GetIndexes() if 0x1000 <= idx <= 0x11FF]
    sdolist = [idx for idx in Node.GetIndexes() if 0x1200 <= idx <= 0x12FF]
    pdolist = [idx for idx in Node.GetIndexes() if 0x1400 <= idx <= 0x1BFF]
    variablelist = [idx for idx in Node.GetIndexes() if 0x2000 <= idx <= 0xBFFF]

#-------------------------------------------------------------------------------
#                       Declaration of the value range types
#-------------------------------------------------------------------------------    
    
    valueRangeContent = ""
    strDefine = "\n#define valueRange_EMC 0x9F /* Type for index 0x1003 subindex 0x00 (only set of value 0 is possible) */"
    strSwitch = """    case valueRange_EMC:
      if (*(UNS8*)value != (UNS8)0) return OD_VALUE_RANGE_EXCEEDED;
      break;\n"""
    internal_types["valueRange_EMC"] = ("UNS8", "", "valueRange_EMC", True)
    num = 0
    for index in rangelist:
        rangename = Node.GetEntryName(index)
        result = range_model.match(rangename)
        if result:
            num += 1
            typeindex = Node.GetEntry(index, 1)
            typename = Node.GetTypeName(typeindex)
            typeinfos = GetValidTypeInfos(typename)
            internal_types[rangename] = (typeinfos[0], typeinfos[1], "valueRange_%d"%num)
            minvalue = Node.GetEntry(index, 2)
            maxvalue = Node.GetEntry(index, 3)
            strDefine += "\n#define valueRange_%d 0x%02X /* Type %s, %s < value < %s */"%(num,index,typeinfos[0],str(minvalue),str(maxvalue))
            strSwitch += "    case valueRange_%d:\n"%(num)
            if typeinfos[3] and minvalue <= 0:
                strSwitch += "      /* Negative or null low limit ignored because of unsigned type */;\n"
            else:
                strSwitch += "      if (*(%s*)value < (%s)%s) return OD_VALUE_TOO_LOW;\n"%(typeinfos[0],typeinfos[0],str(minvalue))
            strSwitch += "      if (*(%s*)value > (%s)%s) return OD_VALUE_TOO_HIGH;\n"%(typeinfos[0],typeinfos[0],str(maxvalue))
            strSwitch += "    break;\n"

    valueRangeContent += strDefine
    valueRangeContent += "\nUNS32 %(NodeName)s_valueRangeTest (UNS8 typeValue, void * value)\n{"%texts
    valueRangeContent += "\n  switch (typeValue) {\n"
    valueRangeContent += strSwitch
    valueRangeContent += "  }\n  return 0;\n}\n"

#-------------------------------------------------------------------------------
#            Creation of the mapped variables and object dictionary
#-------------------------------------------------------------------------------

    mappedVariableContent = ""
    pointedVariableContent = ""
    strDeclareHeader = ""
    strDeclareCallback = ""
    indexContents = {}
    indexCallbacks = {}
    for index in listIndex:
        texts["index"] = index
        strIndex = ""
        entry_infos = Node.GetEntryInfos(index)
        texts["EntryName"] = entry_infos["name"].encode('ascii','replace')
        values = Node.GetEntry(index)
        callbacks = Node.HasEntryCallbacks(index)
        if index in variablelist:
            strIndex += "\n/* index 0x%(index)04X :   Mapped variable %(EntryName)s */\n"%texts
        else:
            strIndex += "\n/* index 0x%(index)04X :   %(EntryName)s. */\n"%texts
        
        # Entry type is VAR
        if not isinstance(values, ListType):
            subentry_infos = Node.GetSubentryInfos(index, 0)
            typename = GetTypeName(Node, subentry_infos["type"])
            typeinfos = GetValidTypeInfos(typename, [values])
            if typename is "DOMAIN" and index in variablelist:
                if not typeinfos[1]:
                    raise ValueError, _("\nDomain variable not initialized\nindex : 0x%04X\nsubindex : 0x00")%index
            texts["subIndexType"] = typeinfos[0]
            if typeinfos[1] is not None:
                texts["suffixe"] = "[%d]"%typeinfos[1]
            else:
                texts["suffixe"] = ""
            texts["value"], texts["comment"] = ComputeValue(typeinfos[2], values)
            if index in variablelist:
                texts["name"] = UnDigitName(FormatName(subentry_infos["name"]))
                strDeclareHeader += "extern %(subIndexType)s %(name)s%(suffixe)s;\t\t/* Mapped at index 0x%(index)04X, subindex 0x00*/\n"%texts
                mappedVariableContent += "%(subIndexType)s %(name)s%(suffixe)s = %(value)s;\t\t/* Mapped at index 0x%(index)04X, subindex 0x00 */\n"%texts
            else:
                strIndex += "                    %(subIndexType)s %(NodeName)s_obj%(index)04X%(suffixe)s = %(value)s;%(comment)s\n"%texts
            values = [values]
        else:
            subentry_infos = Node.GetSubentryInfos(index, 0)
            typename = GetTypeName(Node, subentry_infos["type"])
            typeinfos = GetValidTypeInfos(typename)
            if index == 0x1003:
                texts["value"] = 0
            else:
                texts["value"] = values[0]
            texts["subIndexType"] = typeinfos[0]
            strIndex += "                    %(subIndexType)s %(NodeName)s_highestSubIndex_obj%(index)04X = %(value)d; /* number of subindex - 1*/\n"%texts
            
            # Entry type is RECORD
            if entry_infos["struct"] & OD_IdenticalSubindexes:
                subentry_infos = Node.GetSubentryInfos(index, 1)
                typename = Node.GetTypeName(subentry_infos["type"])
                typeinfos = GetValidTypeInfos(typename, values[1:])
                texts["subIndexType"] = typeinfos[0]
                if typeinfos[1] is not None:
                    texts["suffixe"] = "[%d]"%typeinfos[1]
                    texts["type_suffixe"] = "*"
                else:
                    texts["suffixe"] = ""
                    texts["type_suffixe"] = ""
                texts["length"] = values[0]
                if index in variablelist:
                    texts["name"] = UnDigitName(FormatName(entry_infos["name"]))
                    texts["values_count"] =  str(len(values)-1)
                    strDeclareHeader += "extern %(subIndexType)s%(type_suffixe)s %(name)s[%(values_count)s];\t\t/* Mapped at index 0x%(index)04X, subindex 0x01 - 0x%(length)02X */\n"%texts
                    mappedVariableContent += "%(subIndexType)s%(type_suffixe)s %(name)s[] =\t\t/* Mapped at index 0x%(index)04X, subindex 0x01 - 0x%(length)02X */\n  {\n"%texts
                    for subIndex, value in enumerate(values):
                        sep = ","
                        if subIndex > 0:
                            if subIndex == len(values)-1:
                                sep = ""
                            value, comment = ComputeValue(typeinfos[2], value)
                            if len(value) is 2 and typename is "DOMAIN":
                                raise ValueError("\nDomain variable not initialized\nindex : 0x%04X\nsubindex : 0x%02X"%(index, subIndex))
                            mappedVariableContent += "    %s%s%s\n"%(value, sep, comment)
                    mappedVariableContent += "  };\n"
                else:
                    strIndex += "                    %(subIndexType)s%(type_suffixe)s %(NodeName)s_obj%(index)04X[] = \n                    {\n"%texts
                    for subIndex, value in enumerate(values):
                        sep = ","
                        if subIndex > 0:
                            if subIndex == len(values)-1:
                                sep = ""
                            value, comment = ComputeValue(typeinfos[2], value)
                            strIndex += "                      %s%s%s\n"%(value, sep, comment)
                    strIndex += "                    };\n"
            else:
                
                texts["parent"] = UnDigitName(FormatName(entry_infos["name"]))
                # Entry type is ARRAY
                for subIndex, value in enumerate(values):
                    texts["subIndex"] = subIndex
                    if subIndex > 0:
                        subentry_infos = Node.GetSubentryInfos(index, subIndex)
                        typename = GetTypeName(Node, subentry_infos["type"])
                        typeinfos = GetValidTypeInfos(typename, [values[subIndex]])
                        texts["subIndexType"] = typeinfos[0]
                        if typeinfos[1] is not None:
                            texts["suffixe"] = "[%d]"%typeinfos[1]
                        else:
                            texts["suffixe"] = ""
                        texts["value"], texts["comment"] = ComputeValue(typeinfos[2], value)
                        texts["name"] = FormatName(subentry_infos["name"])
                        if index in variablelist:
                            strDeclareHeader += "extern %(subIndexType)s %(parent)s_%(name)s%(suffixe)s;\t\t/* Mapped at index 0x%(index)04X, subindex 0x%(subIndex)02X */\n"%texts
                            mappedVariableContent += "%(subIndexType)s %(parent)s_%(name)s%(suffixe)s = %(value)s;\t\t/* Mapped at index 0x%(index)04X, subindex 0x%(subIndex)02X */\n"%texts
                        else:
                            strIndex += "                    %(subIndexType)s %(NodeName)s_obj%(index)04X_%(name)s%(suffixe)s = %(value)s;%(comment)s\n"%texts
        
        # Generating Dictionary C++ entry
        if callbacks:
            if index in variablelist:
                name = FormatName(entry_infos["name"])
            else:
                name = "%(NodeName)s_Index%(index)04X"%texts
            name=UnDigitName(name);
            strIndex += "                    ODCallback_t %s_callbacks[] = \n                     {\n"%name
            for subIndex in xrange(len(values)):
                strIndex += "                       NULL,\n"
            strIndex += "                     };\n"
            indexCallbacks[index] = "*callbacks = %s_callbacks; "%name
        else:
            indexCallbacks[index] = ""
        strIndex += "                    subindex %(NodeName)s_Index%(index)04X[] = \n                     {\n"%texts
        for subIndex in xrange(len(values)):
            subentry_infos = Node.GetSubentryInfos(index, subIndex)
            if subIndex < len(values) - 1:
                sep = ","
            else:
                sep = ""
            typename = Node.GetTypeName(subentry_infos["type"])
            if entry_infos["struct"] & OD_IdenticalSubindexes:
                typeinfos = GetValidTypeInfos(typename, values[1:])
            else:
                typeinfos = GetValidTypeInfos(typename, [values[subIndex]])
            if subIndex == 0:
                if index == 0x1003:
                    typeinfos = GetValidTypeInfos("valueRange_EMC")
                if entry_infos["struct"] & OD_MultipleSubindexes:
                    name = "%(NodeName)s_highestSubIndex_obj%(index)04X"%texts
                elif index in variablelist:
                    name = FormatName(subentry_infos["name"])
                else:
                    name = FormatName("%s_obj%04X"%(texts["NodeName"], texts["index"]))
            elif entry_infos["struct"] & OD_IdenticalSubindexes:
                if index in variablelist:
                    name = "%s[%d]"%(FormatName(entry_infos["name"]), subIndex - 1)
                else:
                    name = "%s_obj%04X[%d]"%(texts["NodeName"], texts["index"], subIndex - 1)
            else:
                if index in variablelist:
                    name = FormatName("%s_%s"%(entry_infos["name"],subentry_infos["name"]))
                else:
                    name = "%s_obj%04X_%s"%(texts["NodeName"], texts["index"], FormatName(subentry_infos["name"]))
            if typeinfos[2] == "visible_string":
                sizeof = str(max(len(values[subIndex]), default_string_size))
            elif typeinfos[2] == "domain":
                sizeof = str(len(values[subIndex]))
            else:
                sizeof = "sizeof (%s)"%typeinfos[0]
            params = Node.GetParamsEntry(index, subIndex)
            if params["save"]:
                save = "|TO_BE_SAVE"
            else:
                save = ""
            strIndex += "                       { %s%s, %s, %s, (void*)&%s }%s\n"%(subentry_infos["access"].upper(),save,typeinfos[2],sizeof,UnDigitName(name),sep)
            pointer_name = pointers_dict.get((index, subIndex), None)
            if pointer_name is not None:
                pointedVariableContent += "%s* %s = &%s;\n"%(typeinfos[0], pointer_name, name)
        strIndex += "                     };\n"
        indexContents[index] = strIndex
        
#-------------------------------------------------------------------------------
#                     Declaration of Particular Parameters
#-------------------------------------------------------------------------------

    if 0x1003 not in communicationlist:
        entry_infos = Node.GetEntryInfos(0x1003)
        texts["EntryName"] = entry_infos["name"]
        indexContents[0x1003] = """\n/* index 0x1003 :   %(EntryName)s */
                    UNS8 %(NodeName)s_highestSubIndex_obj1003 = 0; /* number of subindex - 1*/
                    UNS32 %(NodeName)s_obj1003[] = 
                    {
                      0x0	/* 0 */
                    };
                    ODCallback_t %(NodeName)s_Index1003_callbacks[] = 
                     {
                       NULL,
                       NULL,
                     };
                    subindex %(NodeName)s_Index1003[] = 
                     {
                       { RW, valueRange_EMC, sizeof (UNS8), (void*)&%(NodeName)s_highestSubIndex_obj1003 },
                       { RO, uint32, sizeof (UNS32), (void*)&%(NodeName)s_obj1003[0] }
                     };
"""%texts

    if 0x1005 not in communicationlist:
        entry_infos = Node.GetEntryInfos(0x1005)
        texts["EntryName"] = entry_infos["name"]
        indexContents[0x1005] = """\n/* index 0x1005 :   %(EntryName)s */
                    UNS32 %(NodeName)s_obj1005 = 0x0;   /* 0 */
"""%texts

    if 0x1006 not in communicationlist:
        entry_infos = Node.GetEntryInfos(0x1006)
        texts["EntryName"] = entry_infos["name"]
        indexContents[0x1006] = """\n/* index 0x1006 :   %(EntryName)s */
                    UNS32 %(NodeName)s_obj1006 = 0x0;   /* 0 */
"""%texts

    if 0x1014 not in communicationlist:
        entry_infos = Node.GetEntryInfos(0x1014)
        texts["EntryName"] = entry_infos["name"]
        indexContents[0x1014] = """\n/* index 0x1014 :   %(EntryName)s */
                    UNS32 %(NodeName)s_obj1014 = 0x80 + 0x%(NodeID)02X;   /* 128 + NodeID */
"""%texts

    if 0x1016 in communicationlist:
        texts["heartBeatTimers_number"] = Node.GetEntry(0x1016, 0)
    else:
        texts["heartBeatTimers_number"] = 0
        entry_infos = Node.GetEntryInfos(0x1016)
        texts["EntryName"] = entry_infos["name"]
        indexContents[0x1016] = """\n/* index 0x1016 :   %(EntryName)s */
                    UNS8 %(NodeName)s_highestSubIndex_obj1016 = 0;
                    UNS32 %(NodeName)s_obj1016[]={0};
"""%texts
    
    if 0x1017 not in communicationlist:
        entry_infos = Node.GetEntryInfos(0x1017)
        texts["EntryName"] = entry_infos["name"]
        indexContents[0x1017] = """\n/* index 0x1017 :   %(EntryName)s */ 
                    UNS16 %(NodeName)s_obj1017 = 0x0;   /* 0 */
"""%texts
    
    if 0x100C not in communicationlist:
        entry_infos = Node.GetEntryInfos(0x100C)
        texts["EntryName"] = entry_infos["name"]
        indexContents[0x100C] = """\n/* index 0x100C :   %(EntryName)s */ 
                    UNS16 %(NodeName)s_obj100C = 0x0;   /* 0 */
"""%texts
    
    if 0x100D not in communicationlist:
        entry_infos = Node.GetEntryInfos(0x100D)
        texts["EntryName"] = entry_infos["name"]
        indexContents[0x100D] = """\n/* index 0x100D :   %(EntryName)s */ 
                    UNS8 %(NodeName)s_obj100D = 0x0;   /* 0 */
"""%texts

#-------------------------------------------------------------------------------
#               Declaration of navigation in the Object Dictionary
#-------------------------------------------------------------------------------

    strDeclareIndex = ""
    strDeclareSwitch = ""
    strQuickIndex = ""
    quick_index = {}
    for index_cat in index_categories:
        quick_index[index_cat] = {}
        for cat, idx_min, idx_max in categories:
            quick_index[index_cat][cat] = 0
    maxPDOtransmit = 0
    for i, index in enumerate(listIndex):
        texts["index"] = index
        strDeclareIndex += "  { (subindex*)%(NodeName)s_Index%(index)04X,sizeof(%(NodeName)s_Index%(index)04X)/sizeof(%(NodeName)s_Index%(index)04X[0]), 0x%(index)04X},\n"%texts
        strDeclareSwitch += "		case 0x%04X: i = %d;%sbreak;\n"%(index, i, indexCallbacks[index])
        for cat, idx_min, idx_max in categories:
            if idx_min <= index <= idx_max:
                quick_index["lastIndex"][cat] = i
                if quick_index["firstIndex"][cat] == 0:
                    quick_index["firstIndex"][cat] = i
                if cat == "PDO_TRS":
                    maxPDOtransmit += 1
    texts["maxPDOtransmit"] = max(1, maxPDOtransmit)
    for index_cat in index_categories:
        strQuickIndex += "\nconst quick_index %s_%s = {\n"%(texts["NodeName"], index_cat)
        sep = ","
        for i, (cat, idx_min, idx_max) in enumerate(categories):
            if i == len(categories) - 1:
                sep = ""
            strQuickIndex += "  %d%s /* %s */\n"%(quick_index[index_cat][cat],sep,cat)
        strQuickIndex += "};\n"

#-------------------------------------------------------------------------------
#                            Write File Content
#-------------------------------------------------------------------------------

    fileContent = generated_tag + """
#include "%s"
"""%(headerfilepath)

    fileContent += """
/**************************************************************************/
/* Declaration of mapped variables                                        */
/**************************************************************************/
""" + mappedVariableContent

    fileContent += """
/**************************************************************************/
/* Declaration of value range types                                       */
/**************************************************************************/
""" + valueRangeContent

    fileContent += """
/**************************************************************************/
/* The node id                                                            */
/**************************************************************************/
/* node_id default value.*/
UNS8 %(NodeName)s_bDeviceNodeId = 0x%(NodeID)02X;

/**************************************************************************/
/* Array of message processing information */

const UNS8 %(NodeName)s_iam_a_slave = %(iam_a_slave)d;

"""%texts
    if texts["heartBeatTimers_number"] > 0:
        declaration = "TIMER_HANDLE %(NodeName)s_heartBeatTimers[%(heartBeatTimers_number)d]"%texts
        initializer = "{TIMER_NONE" + ",TIMER_NONE" * (texts["heartBeatTimers_number"] - 1) + "}"
        fileContent += declaration + " = " + initializer + ";\n"
    else:
        fileContent += "TIMER_HANDLE %(NodeName)s_heartBeatTimers[1];\n"%texts
    
    fileContent += """
/*
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$

                               OBJECT DICTIONARY

$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
*/
"""%texts
    contentlist = indexContents.keys()
    contentlist.sort()
    for index in contentlist:
        fileContent += indexContents[index]

    fileContent += """
/**************************************************************************/
/* Declaration of pointed variables                                       */
/**************************************************************************/
""" + pointedVariableContent

    fileContent += """
const indextable %(NodeName)s_objdict[] = 
{
"""%texts
    fileContent += strDeclareIndex
    fileContent += """};

const indextable * %(NodeName)s_scanIndexOD (UNS16 wIndex, UNS32 * errorCode, ODCallback_t **callbacks)
{
	int i;
	*callbacks = NULL;
	switch(wIndex){
"""%texts
    fileContent += strDeclareSwitch
    fileContent += """		default:
			*errorCode = OD_NO_SUCH_OBJECT;
			return NULL;
	}
	*errorCode = OD_SUCCESSFUL;
	return &%(NodeName)s_objdict[i];
}

/* 
 * To count at which received SYNC a PDO must be sent.
 * Even if no pdoTransmit are defined, at least one entry is computed
 * for compilations issues.
 */
s_PDO_status %(NodeName)s_PDO_status[%(maxPDOtransmit)d] = {"""%texts

    fileContent += ",".join(["s_PDO_status_Initializer"]*texts["maxPDOtransmit"]) + """};
"""

    fileContent += strQuickIndex
    fileContent += """
const UNS16 %(NodeName)s_ObjdictSize = sizeof(%(NodeName)s_objdict)/sizeof(%(NodeName)s_objdict[0]); 

CO_Data %(NodeName)s_Data = CANOPEN_NODE_DATA_INITIALIZER(%(NodeName)s);

"""%texts

#-------------------------------------------------------------------------------
#                          Write Header File Content
#-------------------------------------------------------------------------------

    texts["file_include_name"] = headerfilepath.replace(".", "_").upper()
    HeaderFileContent = generated_tag + """
#ifndef %(file_include_name)s
#define %(file_include_name)s

#include "CanFestival/data.h"

/* Prototypes of function provided by object dictionnary */
UNS32 %(NodeName)s_valueRangeTest (UNS8 typeValue, void * value);
const indextable * %(NodeName)s_scanIndexOD (UNS16 wIndex, UNS32 * errorCode, ODCallback_t **callbacks);

/* Master node data struct */
extern CO_Data %(NodeName)s_Data;
"""%texts
    HeaderFileContent += strDeclareHeader
    
    HeaderFileContent += "\n#endif // %(file_include_name)s\n"%texts
    
    return fileContent,HeaderFileContent

#-------------------------------------------------------------------------------
#                             Main Function
#-------------------------------------------------------------------------------

def GenerateFile(filepath, node, pointers_dict = {}):
    try:
        headerfilepath = os.path.splitext(filepath)[0]+".h"
        content, header = GenerateFileContent(node, os.path.split(headerfilepath)[1], pointers_dict)
        WriteFile(filepath, content)
        WriteFile(headerfilepath, header)
        return None
    except ValueError, message:
        return _("Unable to Generate C File\n%s")%message


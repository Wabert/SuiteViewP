' Module: frmPolicySegment.frm
' Type: Standard Module
' Stream Path: VBA/frmPolicySegment
' =========================================================

Attribute VB_Name = "frmPolicySegment"
Attribute VB_Base = "0{88C381C5-6534-4296-B04E-A79740661910}{34208E14-E02D-434D-A23D-7F6E6B0837AD}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
'Private colSegItems As Collection
'Private ClusterSegItems As Collection
''Private DB2 As cls_PolicyDB2Data
'Private mLeftMargin As Double
'Private mTopMargin As Double
'Private mRightMargin As Double

'Private mMaxWidth As Double
'
'
'Public Sub classInitialize(PolDB2 As cls_PolicyDB2Data, PolicyRecordID As String)
'Set DB2 = PolDB2
'Set colSegItems = New Collection
'Set ClusterSegItems = New Collection
'mTopMargin = 20
'mLeftMargin = 60
'Me.Height = 300
''mRightMargin =
'mMaxWidth = 480
''ToggleButton1.Visible = False
'
'Select Case PolicyRecordID
'    Case "01": Segment01DataItems: DisplayDataSegment "01 - Basic Section"
'    Case "02": Segment02DataItems: DisplayDataSegment "02 - Coverage"
'    Case "03": Segment03DataItems: DisplayDataSegment "03 - Substandard"
'    Case "04": Segment04DataItems: DisplayDataSegment "04 - Benefits"
'    Case "59": Segment59DataItems: DisplayDataSegment59 "59 - TAMRA"
'
'    Case "60": Segment60DataItems: DisplayDataSegment "60 - Payment Accumulation"
'    Case "63": Segment63DataItems: DisplayDataSegment "63 - Yearly Accumulation"
'    Case "64": Segment64DataItems: DisplayDataSegment "64 - Calendar Year Values"
'    Case "66": Segment66DataItems: DisplayDataSegment "66 - Advanced Product"
'    Case "67": Segment67DataItemCluster: DisplaySegmentClusterData "67 - Renewal Rates"
'    Case "75": Segment75DataItems: DisplayDataSegment "75 - History Values"
'
'    Case "18", "19": Segment18and19DataItems: DisplayDataSegment "18/19 - Coupons and Dividends"
'
'End Select
'
'
'End Sub
'Private Sub DisplayDataSegment(SegmentID As String)
''Builds the form with Segment data found in a single collection (colSegItems).
''This procedure should be used if all the DataItems in colSegItems should have the data count
'
'Dim NewControl As MSForms.Control
'Dim TopPosition As Double
'Dim LeftPosition As Double
'TopPosition = mTopMargin
'LeftPosition = mLeftMargin
'
'
''Add Title bar heading
'CaptionAndHeading SegmentID, TopPosition, LeftPosition
'
'
'Dim xindex As Integer
''Create a loop to cycle through each record in the collection
'For xindex = 1 To colSegItems(1).Count
'
'  'Cycle through all the data Items (fields).  For each data item create and format label and populate value
'  Dim DataItem As Variant
'  For Each DataItem In colSegItems
'    Set NewControl = Me.Controls.Add("Forms.Label.1")
'
'    'Pass NewControl and another new label to DataItem.
'    'The first Control is passed WithEvents to DataItem.  This will allow the double click to pull data associated with DataItem
'    'The second label is needed to display help text when MouseDown occurs on NewControl
'    DataItem.AddControl NewControl, Me.Controls.Add("Forms.Label.1")
'
'    With NewControl
'      .Font.Size = 10
'      .Font.Name = "Arial"
'      .Top = TopPosition
'      .Left = LeftPosition
'      'Populate label value with data
'      .Caption = DataItem.NullZ(xindex, "")
'      .TextAlign = fmTextAlignRight
'      .BorderStyle = fmBorderStyleSingle
'      .BorderColor = &H80000000
'      .Visible = True
'      .AutoSize = True
'
'      'Set position of control
'      ControlPosition NewControl, TopPosition, LeftPosition
'    End With
'  Next
'  'End of current record.  Reset control positions for next record
'  LeftPosition = mLeftMargin
'  TopPosition = TopPosition + NewControl.Height * 2 + 3
'Next
'
'SetScrollBars TopPosition
'End Sub
'
'Private Sub DisplayDataSegment59(SegmentID As String)
''Builds the form with Segment data found in many different collections.  These collections are part of the the collection called ClusterSegItems.
''This procedure should be used if all there are collectoins of DataItems that have different data counts
'
'Dim NewControl As MSForms.Control
'Dim TopPosition As Double
'Dim LeftPosition As Double
'TopPosition = mTopMargin
'LeftPosition = mLeftMargin
'
'
''Add Title bar heading
'CaptionAndHeading SegmentID, TopPosition, LeftPosition
'
'
'Dim colSegItems As Collection
'Set colSegItems = ClusterSegItems("LH_TAMRA_7_PY_PER")
'
'Dim xindex As Integer
''Create a loop to cycle through each record in the collection
'For xindex = 1 To colSegItems(1).Count
'
'  'Cycle through all the data Items (fields).  For each data item create and format label and populate value
'  Dim DataItem As Variant
'  For Each DataItem In colSegItems
'    Set NewControl = Me.Controls.Add("Forms.Label.1")
'
'    'Pass NewControl and another new label to DataItem.
'    'The first Control is passed WithEvents to DataItem.  This will allow the double click to pull data associated with DataItem
'    'The second label is needed to display help text when MouseDown occurs on NewControl
'    DataItem.AddControl NewControl, Me.Controls.Add("Forms.Label.1")
'
'    With NewControl
'      .Font.Size = 10
'      .Font.Name = "Arial"
'      .Top = TopPosition
'      .Left = LeftPosition
'      'Populate label value with data
'      .Caption = DataItem.NullZ(xindex, "")
'      .TextAlign = fmTextAlignRight
'      '.BorderStyle = fmBorderStyleSingle
'      .BorderStyle = fmBorderStyleNone
'      .Visible = True
'      .AutoSize = True
'
'      'Set position of control
'      ControlPosition NewControl, TopPosition, LeftPosition
'    End With
'  Next
'  'End of current record.  Reset control positions for next record
'  LeftPosition = mLeftMargin
'  TopPosition = TopPosition + NewControl.Height * 2 + 3
'Next
'
'
'Set colSegItems = ClusterSegItems("LH_TAMRA_7_PY_YR")
'
''Create a loop to cycle through each record in the collection
'For xindex = 1 To colSegItems(1).Count
'
'  'Cycle through all the data Items (fields).  For each data item create and format label and populate value
'  For Each DataItem In colSegItems
'    Set NewControl = Me.Controls.Add("Forms.Label.1")
'
'    'Pass NewControl and another new label to DataItem.
'    'The first Control is passed WithEvents to DataItem.  This will allow the double click to pull data associated with DataItem
'    'The second label is needed to display help text when MouseDown occurs on NewControl
'    DataItem.AddControl NewControl, Me.Controls.Add("Forms.Label.1")
'
'    With NewControl
'      .Font.Size = 10
'      .Font.Name = "Arial"
'      .Top = TopPosition
'      .Left = LeftPosition
'      'Populate label value with data
'      .Caption = DataItem.NullZ(xindex, "")
'      .TextAlign = fmTextAlignRight
'      '.BorderStyle = fmBorderStyleSingle
'      .BorderStyle = fmBorderStyleNone
'      .Visible = True
'      .AutoSize = True
'
'      'Set position of control
'      ControlPosition NewControl, TopPosition, LeftPosition
'    End With
'  Next
'  'End of current record.  Reset control positions for next record
'  LeftPosition = mLeftMargin
'  TopPosition = TopPosition + NewControl.Height + 3
'Next
'
'
'SetScrollBars TopPosition
'End Sub
'
'Private Sub DisplaySegmentClusterData(SegmentID As String)
''Builds the form with Segment data found in many different collections.  These collections are part of the the collection called ClusterSegItems.
''This procedure should be used if all there are collectoins of DataItems that have different data counts
'
'Dim NewControl As MSForms.Control
'Dim TopPosition As Double
'Dim LeftPosition As Double
'TopPosition = mTopMargin
'LeftPosition = mLeftMargin
'
'
''Add Title bar heading
'CaptionAndHeading SegmentID, TopPosition, LeftPosition
'
'Dim xindex As Integer
'Dim SegItems As Collection
'
'For Each SegItems In ClusterSegItems
'  For xindex = 1 To SegItems(1).Count
'
'    'Cycle through all the data Items.  For each data item create and format label and populate value
'    Dim DataItem As Variant
'    For Each DataItem In SegItems
'
'      Set NewControl = Me.Controls.Add("Forms.Label.1")
'
'      'Pass NewControl and another new label to DataItem.
'      'The first Control is passed WithEvents to DataItem.  This will allow the double click to pull data associated with DataItem
'      'The second label is needed to display help text when MouseDown occurs on NewControl
'      DataItem.AddControl NewControl, Me.Controls.Add("Forms.Label.1")
'
'      With NewControl
'        .Font.Size = 10
'        .Font.Name = "Arial"
'        .Top = TopPosition
'        .Left = LeftPosition
'        'Populate label value with data
'        .Caption = DataItem.NullZ(xindex, "")
'        .TextAlign = fmTextAlignRight
'        '.BorderStyle = fmBorderStyleSingle
'        .BorderStyle = fmBorderStyleNone
'        .Visible = True
'        .AutoSize = True
'
'        'Set position of control
'        ControlPosition NewControl, TopPosition, LeftPosition
'      End With
'   Next
'    'End of current record.  Reset control positions for next record
'    LeftPosition = mLeftMargin
'    TopPosition = TopPosition + NewControl.Height + 2
'  Next
'Next
'
'SetScrollBars TopPosition
'End Sub
'
'
'Private Sub CaptionAndHeading(SegmentIDString As String, ByRef TopPosition As Double, ByRef LeftPosition As Double)
''Add Title bar heading
'Dim strHeading  As String
'strHeading = DB2.CompanyCode & "|" & DB2.PolicyNumber & "|" & DB2.Region & ": " & "[Policy Record " & SegmentIDString & "]"
'Me.Caption = strHeading
'
''Add Heading to form and frame it
'strHeading = DB2.PolicyNumber & ": " & SegmentIDString
'
'Set NewControl = Me.Controls.Add("Forms.Textbox.1")
'  With NewControl
'      .Font.Size = 18
'      .Font.Name = "Arial"
'      .Font.Bold = True
'      .Top = TopPosition - 10
'      .Left = LeftPosition
'      .Value = strHeading
'      .TextAlign = fmTextAlignCenter
'      .BackColor = &H80000004
'      .SpecialEffect = fmSpecialEffectBump
'      .BorderStyle = fmBorderStyleSingle
'      '.BorderStyle = fmBorderStyleNone
'      .Visible = True
'      .AutoSize = True
'      .Width = mMaxWidth + 30
'  End With
'
'
'
' TopPosition = TopPosition + NewControl.Height + 5
'End Sub
'Private Sub ControlPosition(Cntrl As MSForms.Control, ByRef TopPosition As Double, ByRef LeftPosition As Double)
''After AutoSize, check to make sure label still fits and set position for next label
''Position NewControl according to Margin restraints.  Ideally I would like to produce
''a layout similar to online Cyberlife screens
'With Cntrl
'  If LeftPosition + .Width - mLeftMargin + 5 > mMaxWidth Then
'    LeftPosition = mLeftMargin
'    TopPosition = TopPosition + .Height + 3
'    .Top = TopPosition
'    .Left = LeftPosition
'  End If
'
'  LeftPosition = LeftPosition + Cntrl.Width + 5
'End With
'End Sub
'Private Sub SetScrollBars(ByRef TopPosition As Double)
'
'If TopPosition > Me.Height Then
'    With Me
'      'This will create a vertical scrollbar
'      .ScrollBars = fmScrollBarsVertical
'
'      'Change the values Per your requirements
'      .ScrollHeight = TopPosition
'      .ScrollWidth = .InsideWidth * 9
'    End With
'End If
'End Sub
'
'
'Private Sub Segment01DataItems()
'
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "STD_PRM_PRC_IND")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "TRD_POL_ANU_IND")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "POL_1035_XCG_IND")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "TAMRA_GDF_IND")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "IDT_PRM_IND")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "ATM_FLE_MNT_IND")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "STA_CHG_IND")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "OL_FLE_MNT_IND")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "NON_TRD_POL_IND")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "ICL_IN_POL_CNT_IND")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "FXD_PRM_IND")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "TFDF_GDL_IND")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "VAR_FND_ELG_IND")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "RES_CPE_CLC_IND")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "CB_1035_IND")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "CB_1035_OVER_IND")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "CK_POLICY_NBR")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "ISS_CMP_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "ADM_CMP_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "FIN_CMP_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "ACY_POL_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "INT_MLV_NBR")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "PRM_PAID_TO_DT")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "PRM_BILL_TO_DT")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "APP_WRT_DT")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "LST_ANV_DT")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "BIL_DAY_NBR")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "BIL_DAY_USE_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "NFO_OPT_TYP_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "APL_PRC_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "APL_LIM_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "LN_TYP_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "LN_PLN_ITS_RT")
'colSegItems.Add DB2.DataItem("LH_FXD_PRM_POL", "APL_CNT_QTY")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "ASN_IND_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "RTT_1_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "PRI_DIV_OPT_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "DIV_2ND_OPT_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "PRI_OTH_FRM_OPT_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "OTH_FRM_2ND_OPT_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "PEN_TST_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "REINSURED_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "PAY_CTR_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "PRM_PAY_ST_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "PAY_TAX_DST_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "SVC_AGC_NBR")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "SVC_AGT_NBR")
'colSegItems.Add DB2.DataItem("LH_FXD_PRM_POL", "MD_PRM_SRC_CD")
'colSegItems.Add DB2.DataItem("LH_FXD_PRM_POL", "SAN_MD_FCT")
'colSegItems.Add DB2.DataItem("LH_FXD_PRM_POL", "QTR_MD_FCT")
'colSegItems.Add DB2.DataItem("LH_FXD_PRM_POL", "MO_MD_FCT")
'colSegItems.Add DB2.DataItem("LH_FXD_PRM_POL", "MD_PRM_MUL_ORD_CD")
'colSegItems.Add DB2.DataItem("LH_FXD_PRM_POL", "RT_FCT_ORD_CD")
'colSegItems.Add DB2.DataItem("LH_FXD_PRM_POL", "ROU_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_FXD_PRM_POL", "POL_FEE_MDF_CD")
'colSegItems.Add DB2.DataItem("LH_FXD_PRM_POL", "COL_FEE_MDF_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "PRM_DSC_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "NSD_MD_CD")
'colSegItems.Add DB2.DataItem("LH_FXD_PRM_POL", "COL_FEE_ADD_CD")
'colSegItems.Add DB2.DataItem("LH_FXD_PRM_POL", "COL_FEE_COM_CD")
'colSegItems.Add DB2.DataItem("LH_FXD_PRM_POL", "COL_FEE_AMT")
'colSegItems.Add DB2.DataItem("LH_FXD_PRM_POL", "POL_FEE_FCT_SRC_CD")
'colSegItems.Add DB2.DataItem("LH_FXD_PRM_POL", "POL_FEE_ADD_CD")
'colSegItems.Add DB2.DataItem("LH_FXD_PRM_POL", "POL_FEE_COM_CD")
'colSegItems.Add DB2.DataItem("LH_FXD_PRM_POL", "POL_FEE_USR_CD")
'colSegItems.Add DB2.DataItem("LH_FXD_PRM_POL", "POL_FEE_AMT")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "POL_PRM_AMT")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "PRM_COM_MTH_CD")
'colSegItems.Add DB2.DataItem("LH_FXD_PRM_POL", "SPE_COM_ARG_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "SPE_BIL_HDL_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "FST_SKIP_MO_NBR")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "MO_TO_SKIP_NBR")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "SUS_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "PRM_PAY_STA_REA_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "BIL_FRM_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "PMT_FQY_PER")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "BIL_CRY_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "BIL_LGG_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "OGN_ETR_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "LST_ETR_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "POL_CHG_RPT_TYP_CD")
'colSegItems.Add DB2.DataItem("LH_FXD_PRM_POL", "LST_PRM_PAY_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "LST_ACT_TRS_DT")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "LST_FIN_DT")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "LST_POL_CHG_DT")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "LST_BIL_ERT_DT")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "BIL_ERT_TYP_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "USR_RES_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "ISS_CTR_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "POL_ISS_ST_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "MEC_STATUS_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "COM_CHARGEBACK_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "DTH_BNF_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "EIL_IND")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "PND_STA_REA_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "POL_CTT_TYP_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "GRP_HST_IND")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "PW_OPT_CD")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "OFL_PRC_REQ_DT")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "NXT_BIL_DT")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "PLN_TMN_DT")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "NXT_SCH_NOT_DT")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "NXT_SCH_STT_DT")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "NXT_MVRY_PRC_DT")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "NXT_YR_END_PRC_DT")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "DIV_ACY_CLC_DT")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "NXT_IND_INC_DT")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "ADVANCE_IND")
'colSegItems.Add DB2.DataItem("LH_BAS_POL", "SPEC_CASE_IND")
'colSegItems.Add DB2.DataItem("TH_BAS_POL", "BLDY_KEYWORD_IND")
'colSegItems.Add DB2.DataItem("TH_BAS_POL", "ARCH_RESTR_CODE")
'colSegItems.Add DB2.DataItem("TH_BAS_POL", "BILL_DAY_1")
'colSegItems.Add DB2.DataItem("TH_BAS_POL", "BILL_DAY_2")
'colSegItems.Add DB2.DataItem("TH_BAS_POL", "FORCED_PREM_IND")
'colSegItems.Add DB2.DataItem("TH_BAS_POL", "LOAN_INT_SEL")
'colSegItems.Add DB2.DataItem("TH_BAS_POL", "LUS_IND")
'colSegItems.Add DB2.DataItem("TH_BAS_POL", "REIN_MAX_XEEDED")
'colSegItems.Add DB2.DataItem("TH_BAS_POL", "REVIEW_NEED_IND")
'
'
'End Sub
'
'Private Sub Segment02DataItems()
'
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "ADV_PRD_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "PTR_IN_SCL_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "ATM_ICE_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "COV_REETR_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "UNT_REQ_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "COV_AMT_REQ_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "POL_FRM_INP_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "ANN_PRM_INP_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "INT_TRM_ALW_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "IVD_COV_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "COV_RVL_RQR_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "COM_PHA_INP_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "CEA_DT_INP_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "TAMRA_GDF_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "FOC_1035_XCG_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "FOC_UNISEX_OVR_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "FOC_BAN_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "EIL_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "IF_POL_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "EIL_POL_FEE_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "BAS_COV_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "AP_TRM_RID_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "BLIR_PUA_CHG_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "DCA_FCA_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "DTH_BEN_ADJ_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "COV_PHA_NBR")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "PRD_LIN_TYP_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "RID_STA_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "NXT_CHG_DT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "NXT_CHG_TYP_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "COM_BAS_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "AGT_COM_PHA_NBR")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "MTL_FCT_TBL_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "NBR_OF_LIVES_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "MTL_FUN_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "RES_ITS_RT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "VAL_MTH_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "INS_CLS_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "PLN_BSE_SRE_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "LIF_PLN_SUB_SRE_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "AH_ACC_ELM_PER_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "AH_SIC_ELM_PER_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "LIF_FURTHER_DES_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "AH_ACC_BNF_PER_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "AH_SIC_BNF_PER_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "DTH_BNF_EFF_AGE")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "RID_COI_BAN_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "AH_DED_AMT_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "DFI_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "RET_OF_PRM_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "INS_SEX_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "INS_ISS_AGE")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "TRUE_AGE")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "AGE_USE_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "AGE_SRC_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "LIVES_COV_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "ISSUE_DT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "PAY_UP_DT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "COV_MT_EXP_DT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "COV_UNT_QTY")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "COV_VPU_AMT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "DCA_TRM_ITS_RT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "DCA_TRM_VPU_CUM_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "DCA_TRM_LVL_YR_DUR")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "ANU_PUR_VAL_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "ANU_QFY_TYP_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "ANU_SET_OPT_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "ANU_AT_ISS_DUR_NBR")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "RET_PRM_UNT_AMT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "ANN_PRM_UNT_AMT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "COV_NFO_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "CSH_VAL_YR")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "ADJ_ETI_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "RPU_BNF_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "EI_INT_AMT_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "RMD_PAYOUT_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "EI_BNF_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "RMD_CLC_MTH_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "MAJ_LIN_OF_BUS_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "ETR_SRC_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "RT_BK_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "COV_MED_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "VAL_USE_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "LOW_DUR_PER")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "LOW_DUR_CSV_AMT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "LOW_DUR_1_CSV_AMT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "LOW_DUR_2_CSV_AMT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "LOW_DUR_3_CSV_AMT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "ORG_LTC_UNT_QTY")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "ORG_LTC_VPU_AMT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "CPI_IFT_FCT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "OGN_SPC_UNT_QTY")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "FXD_ANU_BIL_AMT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "FTD_RID_PLN_OPT_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "FTD_RID_CDR_AMT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "FTD_RID_AT_RSK_AMT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "LOW_DUR_NSP_AMT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "LOW_DUR_1_NSP_AMT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "LOW_DUR_2_NSP_AMT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "REFRESH_OR_RNL_AGE")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "NSP_EI_TBL_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "NSP_RPU_TBL_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "NSP_ITS_RT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "RID_XPN_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "SUTB_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "PRS_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "PRS_SEQ_NBR")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "CEA_REA_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "AGE_CLC_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "MEC_STA_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "GUA_ISS_IND")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "RENEWABLE_PRM_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "INT_RNL_PER")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "SBQ_RNL_STR_DUR")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "SBQ_RNL_PER")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "IDT_PRM_GUA_PER")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "LNG_TRM_CLM_TYP_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "PREMIUM_RESID_CD  ")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "UNISEX_OVR_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "UNISEX_SEX_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "UNISEX_SSR_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "UNISEX_GUA_RT_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "POL_FRM_NBR")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "PLN_DES_SER_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "PDF_KEY_VERSION_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "PDF_KEY_EFF_DT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "EFF_DT_OVERRIDE_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "IAF_KEY_VERSION_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "COM_PLN_GRP_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "COM_PLN_VTN_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "COM_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "PRD_VAL_USE_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "PRD_AMT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "PRD_PCT")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "MDRT_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "VAL_TBL_RFR_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "JNT_ISU_MTL_TBL_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "JNT_ISU_ISS_AGE")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "BAN_STRUCTURE_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "DIV_PTP_TYP_CD")
'colSegItems.Add DB2.DataItem("LH_COV_PHA", "GUA_PTP_APP_OPT_CD")
'colSegItems.Add DB2.DataItem("TH_COV_PHA", "AN_PRD_ID")
'colSegItems.Add DB2.DataItem("TH_COV_PHA", "OPT_EXER_IND")
'colSegItems.Add DB2.DataItem("TH_COV_PHA", "COLA_INCR_IND")
'
'End Sub
'
'Private Sub Segment03DataItems()
'
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "LIF_OR_COV_MTH_CD")
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "INP_XTR_PRM_IND")
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "VLD_IND")
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "CUR_COI_VAL_TYP_CD")
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "XTR_TMP_OR_PMN_CD")
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "IF_POL_IND")
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "COV_PHA_NBR")
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "SST_XTR_TYP_CD")
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "SST_XTR_SBY_CD")
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "PRS_CD")
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "PRS_SEQ_NBR")
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "SST_XTR_CEA_DT")
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "SST_CEA_DT_TYP_CD")
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "SST_XTR_COM_CD")
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "SST_XTR_RT_TBL_CD")
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "SST_XTR_REA_CD")
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "RES_MTH_PLN_CD")
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "SST_XTR_UNT_AMT")
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "XTR_PER_1000_AMT")
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "SST_XTR_PCT")
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "SST_XTR_CEA_DUR")
'colSegItems.Add DB2.DataItem("LH_SST_XTR_CRG", "SST_XTR_EFF_DT")
'colSegItems.Add DB2.DataItem("TH_SST_XTR_CRG", "COM_TABLE_RATE")
'colSegItems.Add DB2.DataItem("TH_SST_XTR_CRG", "CONTENT_CODE")
'colSegItems.Add DB2.DataItem("TH_SST_XTR_CRG", "PREM_DISCNT_IND")
'
'End Sub
'
'Private Sub Segment04DataItems()
'
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "IF_POL_IND")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "MAT_EXTN_IND")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "CEA_DT_INP_IND")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "BNF_NBR_LIVES_CD")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "PW_PCT_IND")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "DCA_FCA_IND")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "STP_BAN_IND")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "BNF_SEG_IVD_IND")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "UNT_REQ_IND")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "BNF_REQ_MTH_IND")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "INP_FRM_NBR_IND")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "INP_BNF_PRM_IND")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "INT_TRM_IND")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "IHT_BNF_IND")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "BNF_VLD_IND")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "BNF_DENIED_IND")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "COV_PHA_NBR")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "SPM_BNF_TYP_CD")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "SPM_BNF_SBY_CD")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "PRS_CD")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "PRS_SEQ_NBR")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "BNF_CEA_DT")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "BNF_STA_CD")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "COL_ICE_FQY_CD")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "BNF_COM_CD")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "RES_MTH_PLN_CD")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "BNF_ISS_AGE")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "AGE_SRC_CD")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "BNF_ISS_DT")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "BNF_PAY_UP_DT")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "BNF_RT_FCT")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "BNF_ANN_PPU_AMT")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "BNF_PRM_CLC_PCT")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "BNF_UNT_QTY")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "BNF_VPU_AMT")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "BNF_OGN_CEA_DT")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "RNL_RT_IND")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "BNF_FRM_NBR")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "OPT_DT")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "IFT_PCT")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "CPI_ADJ_REJ_NBR")
'colSegItems.Add DB2.DataItem("LH_SPM_BNF", "PRT_PCT")
'colSegItems.Add DB2.DataItem("TH_SPM_BNF", "BENEFIT_FREQ")
'colSegItems.Add DB2.DataItem("TH_SPM_BNF", "AUTO_RATE_DENY")
'
'End Sub
'
'Private Sub Segment18and19DataItems()
'
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "CK_PTP_TYP_CD")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "APP_PTP_IND")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "PTP_ANV_PRC_IND")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "RPU_VAL_IND")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "CUR_VAL_IND")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "PRJ_VAL_IND")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "PTP_SRC_IND")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "LN_RDU_IND")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "FLE_MNT_IND")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "DIR_RCG_ADJ_IND")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "TMN_DIV_IND")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "COV_PHA_NBR")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "ERN_DT_MO_YR_NBR")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "ERN_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "PRO_RATA_LIA_CD")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "DEP_NF_CD")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "PUA_NF_CD")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "OYT_NF_CD")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "OPT_RTT_CD")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "UNAPPLIED_HST_IND")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "DEP_ITS_RT")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "PUA_MTL_TBL_CD")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "PUA_ITS_RT")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "PUA_CLS_CD")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "OYT_MTL_TBL_CD")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "OYT_ITS_RT")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "OYT_CLS_CD")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "PUA_MT_DUR")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "CSH_AMT")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "PUA_AMT")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "OYT_AMT")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "PRJ_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "PRJ_CSH_AMT")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "DIR_RCG_DIV_IND")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "DIV_GRS_ITS_RT")
'colSegItems.Add DB2.DataItem("LH_UNAPPLIED_PTP", "PUA_UNT_QTY")
'
'End Sub
'
'Private Sub Segment59DataItems()
'Set colSubset1 = New Collection
'Set colSubset2 = New Collection
''Set colSubSet3 = New Collection
'
'colSubset1.Add DB2.DataItem("LH_TAMRA_7_PY_PER", "GDF_SVPY_TES_IND")
'colSubset1.Add DB2.DataItem("LH_TAMRA_7_PY_PER", "GDF_GDL_PRM_IND")
'colSubset1.Add DB2.DataItem("LH_TAMRA_7_PY_PER", "MAT_CHG_IND")
'colSubset1.Add DB2.DataItem("LH_TAMRA_7_PY_PER", "SVPY_PRM_CLC_IND")
'colSubset1.Add DB2.DataItem("LH_TAMRA_7_PY_PER", "REVERSE_TO_ISS_IND")
'colSubset1.Add DB2.DataItem("LH_TAMRA_7_PY_PER", "OVR_MEC_IND")
'colSubset1.Add DB2.DataItem("LH_TAMRA_7_PY_PER", "MEC_STA_CD")
'colSubset1.Add DB2.DataItem("LH_TAMRA_7_PY_PER", "TAMRA_SST_RT_CD")
'colSubset1.Add DB2.DataItem("LH_TAMRA_7_PY_PER", "TAMRA_MEC_EFF_DT")
'colSubset1.Add DB2.DataItem("LH_TAMRA_7_PY_PER", "SVPY_PER_STR_DT")
'colSubset1.Add DB2.DataItem("LH_TAMRA_7_PY_PER", "SVPY_NXT_CHG_DT")
'colSubset1.Add DB2.DataItem("LH_TAMRA_7_PY_PER", "SVPY_LVL_PRM_AMT")
'colSubset1.Add DB2.DataItem("LH_TAMRA_7_PY_PER", "SVPY_WDW_PRM_AMT")
'colSubset1.Add DB2.DataItem("LH_TAMRA_7_PY_PER", "TAMRA_ITS_RT")
'colSubset1.Add DB2.DataItem("LH_TAMRA_7_PY_PER", "TAMRA_GUA_PER")
'colSubset1.Add DB2.DataItem("LH_TAMRA_7_PY_PER", "SVPY_BEG_FCE_AMT")
'colSubset1.Add DB2.DataItem("LH_TAMRA_7_PY_PER", "SVPY_BEG_CSV_AMT")
'colSubset1.Add DB2.DataItem("LH_TAMRA_7_PY_PER", "GDF_DTH_BNF_1_AMT")
'colSubset1.Add DB2.DataItem("LH_TAMRA_7_PY_PER", "GDF_DTH_BNF_2_AMT")
'colSubset1.Add DB2.DataItem("LH_TAMRA_7_PY_PER", "XCG_1035_PMT_QTY")
'
'colSubset2.Add DB2.DataItem("LH_TAMRA_7_PY_YR", "SVPY_YR_SEQ_NBR")
'colSubset2.Add DB2.DataItem("LH_TAMRA_7_PY_YR", "SVPY_PRM_PAY_AMT")
'colSubset2.Add DB2.DataItem("LH_TAMRA_7_PY_YR", "SVPY_WTD_AMT")
'
''colSubSet3.Add DB2.DataItem("LH_TAMRA_MEC_PRM", "COV_PHA_NBR")
''colSubSet3.Add DB2.DataItem("LH_TAMRA_MEC_PRM", "GDL_PRM_SER_NBR")
''colSubSet3.Add DB2.DataItem("LH_TAMRA_MEC_PRM", "SVPY_PRM_SER_NBR")
'
'ClusterSegItems.Add colSubset1, "LH_TAMRA_7_PY_PER"
'ClusterSegItems.Add colSubset2, "LH_TAMRA_7_PY_YR"
'
''Populate colSegItems so there is one collection with all the data items.  this will be used if labels on all data items need to be adjusted or updated
'Dim item
'For Each CollectionItem In ClusterSegItems
'  For Each item In CollectionItem
'   colSegItems.Add item
'  Next
'Next
'
'
'
'End Sub
'
'Private Sub Segment60DataItems()
'
'colSegItems.Add DB2.DataItem("LH_POL_TOTALS", "TOT_REG_PRM_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_TOTALS", "TOT_ADD_PRM_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_TOTALS", "TOT_ADD_PRM_QTY")
'colSegItems.Add DB2.DataItem("LH_POL_TOTALS", "TOT_PRM_LD_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_TOTALS", "HI_YR_TOT_PRM_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_TOTALS", "TOT_PRM_TAX_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_TOTALS", "TOT_TAX_PRM_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_TOTALS", "TOT_FRS_YR_PRM_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_TOTALS", "TOT_WTD_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_TOTALS", "TOT_WTD_CRG_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_TOTALS", "TOT_WTD_QTY")
'colSegItems.Add DB2.DataItem("LH_POL_TOTALS", "POL_CST_BSS_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_TOTALS", "ANU_ITS_ICM_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_TOTALS", "ANU_CST_BSS_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_TOTALS", "LST_CRG_FRE_WTD_DT")
'colSegItems.Add DB2.DataItem("LH_POL_TOTALS", "LST_MVA_FRE_WTD_DT")
'colSegItems.Add DB2.DataItem("LH_POL_TOTALS", "MVA_CSV_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_TOTALS", "TOT_FRE_WTD_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_TOTALS", "TOT_FRE_WTD_PCT")
'colSegItems.Add DB2.DataItem("LH_POL_TOTALS", "TOT_RED_FEE_AMT")
'colSegItems.Add DB2.DataItem("LH_MO_ADD_PMT", "MO_SEQ_NBR")
'colSegItems.Add DB2.DataItem("LH_MO_ADD_PMT", "MO_ADD_PRM_AMT")
'
'End Sub
'
'Private Sub Segment63DataItems()
'
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "REVS_PRC_GEN_IND")
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "POL_YR_DUR")
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "POL_TOT_CSV_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "YTD_TOT_PMT_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "YTD_ADD_PRM_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "YTD_ADD_PRM_QTY")
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "YTD_PRM_TAX_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "YTD_CRE_ITS_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "YTD_GUA_RT_ITS_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "YTD_WTD_NBR")
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "YTD_CSV_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "YTD_TRF_QTY")
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "YTD_ALC_CHG_QTY")
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "YTD_FRE_WTD_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "CHG_FREE_WDWL_PCT")
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "YTD_MVA_FRE_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "FND_BEG_YR_BAL_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "FND_TRS_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "FND_TRS_CNT_QTY")
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "BEG_YR_VAR_ACT_BAL")
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "CRY_FWD_FRE_WD_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_YR_TOT", "CRY_FWD_FRE_WD_PCT")
'
'End Sub
'
'Private Sub Segment64DataItems()
'
'colSegItems.Add DB2.DataItem("LH_POL_CAL_YR_TOT", "CAL_YR_ADD_PRM_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_CAL_YR_TOT", "CAL_YR_END_DT")
'colSegItems.Add DB2.DataItem("LH_POL_CAL_YR_TOT", "CAL_YR_NET_WTD_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_CAL_YR_TOT", "CAL_YR_REG_PRM_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_CAL_YR_TOT", "CAL_YR_WTD_CRG_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_CAL_YR_TOT", "INT_LIFE_FCT")
'colSegItems.Add DB2.DataItem("LH_POL_CAL_YR_TOT", "LOANED_CSV_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_CAL_YR_TOT", "REG_MIN_DTB_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_CAL_YR_TOT", "RMD_CLC_IND")
'colSegItems.Add DB2.DataItem("LH_POL_CAL_YR_TOT", "RMD_DEFERRED_IND")
'colSegItems.Add DB2.DataItem("LH_POL_CAL_YR_TOT", "RMD_NOT_IND")
'colSegItems.Add DB2.DataItem("LH_POL_CAL_YR_TOT", "RMD_REMINDER_IND")
'colSegItems.Add DB2.DataItem("LH_POL_CAL_YR_TOT", "RQR_MIN_DTB_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_CAL_YR_TOT", "UNLOANED_CSV_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_CAL_YR_TOT", "YR_END_ACT_BAL_IND")
'colSegItems.Add DB2.DataItem("LH_POL_CAL_YR_TOT", "CAL_YR_NRG_PRM_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_CAL_YR_TOT", "PV_ADDL_BENS")
'
'End Sub
'
'
'Private Sub Segment65DataItems()
'
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "TCH_POL_ID")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "CK_CMP_CD")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "CK_SYS_CD")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "IMPAIRED_IND")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "OVR_ITS_CRE_RT_IND")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "MVA_FND_IND")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "MVA_XCS_ITS_IND")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "HST_IND")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "TEFRA_OR_TAMRA_IND")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "PST_TAX_MNY_IND")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "POL_LVL_DTA_IND")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "ACT_ERT_RQR_IND")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "COM_ERT_RQR_IND")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "POL_EXH_RQR_IND")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "ACT_ERT_GNR_IND")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "COM_ERT_GNR_IND")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "POL_EXH_GNR_IND")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "MVRY_PRC_CPL_IND")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "COV_PHA_NBR")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "FND_ID_CD")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "FND_VAL_PHA_NBR")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "FND_TYP_CD")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "MVRY_DT")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "ITS_RT_STR_DT")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "ITS_PER_STR_DT")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "ITS_PER_END_DT")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "VAL_STR_DT")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "VAL_CUR_ASOF_DT")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "PER_OR_IVM_DUR")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "VAL_PHA_ITS_RT")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "CSV_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "FND_UNT_QTY")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "NET_DOL_OF_PMT_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "CRG_DED_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "TOT_CRE_ITS_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "PRE_US_RGL_UNT_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "GUA_RT_ERN_ITS_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_FND_VAL_TOT", "PRE_TAMRA_DOL_AMT")
'
'End Sub
'
'Private Sub Segment66DataItems()
'
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "OL_ACY_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "ICP_ACY_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PR_LIMIT_EXC_ONL")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "REVS_ACY_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "IN_GRA_PER_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "FIN_HST_FQY_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PRM_WAV_ON_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PRM_WAV_OFF_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "LN_PSN_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "GUA_LN_PSN_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "GUA_LN_PRC_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "GRA_PER_NOT_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "LN_ITS_BIL_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PRM_TAX_QFY_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "DIF_BIL_PRM_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "FUL_SRD_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PHD_STT_BSS_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "GRA_PER_EXT_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "MT_DT_REQ_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "INT_OR_ROLL_PRM_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "COV_VAL_ACU_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "STT_FQY_REQ_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "CNFM_FQY_OVR_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PLN_INT_PRM_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "STT_BSS_OVR_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "TFDF_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "DTH_BNF_PLN_OPT_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "DCA_ORD_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "DCA_PLN_OPT_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "ICE_ORD_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "ICE_PLN_OPT_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "MT_DT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "MIN_CSV_BAL_AMT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "MIN_CSV_BAL_ITS_RT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "POL_GUA_ITS_RT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "CSV_XPN_FQY_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "CSV_XPN_BSS_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "CSV_XPN_TBL_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "CSV_XPN_RLE_1_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "CSV_XPN_RLE_2_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "CSV_XPN_RLE_3_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "CINS_NAR_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "CINS_GUA_RT_PER_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "CINS_GUA_RT_PER")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "CINS_GUA_END_DT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "CINS_CRG_FQY_PER")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "CINS_RT_CLC_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "CINS_CRG_THRU_DT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PRM_REC_ITS_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PRM_GRA_PER")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PRM_FREEZE_PER")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PRM_LD_TBL_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PRM_LD_RLE_1_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PRM_LD_RLE_2_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PRM_LD_RLE_3_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "MAX_ADD_PMT_NBR")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "ADD_PMT_DBT_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "ADD_PMT_MIN_AMT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "ADD_PMT_MAX_AMT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "ADD_PMT_MAX_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PRM_TAX_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "BIL_PLN_OPT_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "BIL_STA_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "BIL_COMMENCE_DT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "REN_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "COM_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "CDR_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "CDR_AMT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "CDR_PCT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "MIN_SUM_ISU_AMT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "NAR_AMT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "DEATH_BEN_AMT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "ANN_STT_FQY_PER")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "CNFM_FQY_PER")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "FUL_SRD_ALW_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "FUL_SRD_PTA_IND")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "FUL_SRD_CRG_TBL_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "FUL_SRD_FST_CRG_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "FUL_SRD_2ND_CRG_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "FRE_LK_SRD_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PAT_SRD_ALW_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PAT_SRD_CRG_TBL_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PAT_SRD_FST_CRG_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PAT_SRD_2ND_CRG_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "MIN_PAT_SRD_AMT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PAT_SRD_MAX_NBR")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PAT_SRD_MIN_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PAT_SRD_MIN_MO_NBR")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PAT_SRD_BAL_AMT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "LN_ITS_DSB_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "LN_CRE_ITS_RT_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "LN_CRE_ITS_RT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "LN_MIN_BAL_TBL_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "LN_MIN_BAL_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "LN_MIN_DUR")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "LN_MIN_AMT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PRF_LN_OPT_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PRF_LN_AMT_PCT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PRF_LN_YR_AVA_NBR")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PRF_LN_ITS_CRG_RT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PRF_LN_ITS_CRE_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PRF_LN_ITS_CRE_RT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "LST_MO_DUR_PRC_NBR")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "GRA_PER_DAY_NBR")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "GRA_PER_ITS_RT_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "GRA_PER_CRE_RT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "GRA_THD_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "GRA_PER_EXP_DT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "LST_STT_DT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "LST_STT_TYP_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PRC_BACK_DT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "LST_MO_DUR_NBR")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "ARCH_HST_DUR_NBR")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "REWARD_TYP_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "REWARD_TBL_AGU_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PRO_BNS_RS_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PRO_BNS_RS_DT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "RETRO_BNS_RS_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "RETRO_BNS_RS_DT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "GLP_CUR_RT_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "THD_AMT")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "GUA_WTD_PER_RLE_CD")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "GUA_WTD_PER")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "WAIVER_AMT_FREEZE")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "RFA_IND")
'colSegItems.Add DB2.DataItem("TH_NON_TRD_POL", "PND_DCA_CRG_IND")
'colSegItems.Add DB2.DataItem("TH_NON_TRD_POL", "DECR_CHRG_ALLOW")
'colSegItems.Add DB2.DataItem("LH_NON_TRD_POL", "PLVL_GAV_RULE")
'
'End Sub
'
'
'Private Sub Segment67DataItemCluster()
'Set colSubset1 = New Collection
'Set colSubset2 = New Collection
'Set colSubSet3 = New Collection
'Set colSubSet4 = New Collection
'Set colSubSet5 = New Collection
'Set colSubSet6 = New Collection
'Set colSubSet7 = New Collection
'
'colSubset1.Add DB2.DataItem("LH_BNF_INS_GDL_PRM", "COV_PHA_NBR")
'colSubset1.Add DB2.DataItem("LH_BNF_INS_GDL_PRM", "PRS_CD")
'colSubset1.Add DB2.DataItem("LH_BNF_INS_GDL_PRM", "PRS_SEQ_NBR")
'colSubset1.Add DB2.DataItem("LH_BNF_INS_GDL_PRM", "RT_CLS_CD")
'colSubset1.Add DB2.DataItem("LH_BNF_INS_GDL_PRM", "SEG_IDX_NBR")
'colSubset1.Add DB2.DataItem("LH_BNF_INS_GDL_PRM", "PRM_RT_TYP_CD")
'colSubset1.Add DB2.DataItem("LH_BNF_INS_GDL_PRM", "SPM_BNF_TYP_CD")
'colSubset1.Add DB2.DataItem("LH_BNF_INS_GDL_PRM", "SPM_BNF_SBY_CD")
'colSubset1.Add DB2.DataItem("LH_BNF_INS_GDL_PRM", "RT_SEX_CD")
'colSubset1.Add DB2.DataItem("LH_BNF_INS_GDL_PRM", "GDL_PRM_AMT")
'colSubset1.Add DB2.DataItem("LH_BNF_INS_GDL_PRM", "GDL_PRM_UNT_QTY")
'colSubset2.Add DB2.DataItem("LH_BNF_INS_RNL_RT", "COV_PHA_NBR")
'colSubset2.Add DB2.DataItem("LH_BNF_INS_RNL_RT", "PRS_CD")
'colSubset2.Add DB2.DataItem("LH_BNF_INS_RNL_RT", "PRS_SEQ_NBR")
'colSubset2.Add DB2.DataItem("LH_BNF_INS_RNL_RT", "SEG_IDX_NBR")
'colSubset2.Add DB2.DataItem("LH_BNF_INS_RNL_RT", "PRM_RT_TYP_CD")
'colSubset2.Add DB2.DataItem("LH_BNF_INS_RNL_RT", "SPM_BNF_SBY_CD")
'colSubset2.Add DB2.DataItem("LH_BNF_INS_RNL_RT", "SPM_BNF_TYP_CD")
'colSubset2.Add DB2.DataItem("LH_BNF_INS_RNL_RT", "RT_SEX_CD")
'colSubset2.Add DB2.DataItem("LH_BNF_INS_RNL_RT", "RT_CLS_CD")
'colSubset2.Add DB2.DataItem("LH_BNF_INS_RNL_RT", "RT_BAN_CD")
'colSubset2.Add DB2.DataItem("LH_BNF_INS_RNL_RT", "RNL_RT")
'colSubSet3.Add DB2.DataItem("LH_COV_INS_GDL_PRM", "COV_PHA_NBR")
'colSubSet3.Add DB2.DataItem("LH_COV_INS_GDL_PRM", "PRS_CD")
'colSubSet3.Add DB2.DataItem("LH_COV_INS_GDL_PRM", "PRS_SEQ_NBR")
'colSubSet3.Add DB2.DataItem("LH_COV_INS_GDL_PRM", "SEG_IDX_NBR")
'colSubSet3.Add DB2.DataItem("LH_COV_INS_GDL_PRM", "PRM_RT_TYP_CD")
'colSubSet3.Add DB2.DataItem("LH_COV_INS_GDL_PRM", "SYS_CLC_PRM_IND")
'colSubSet3.Add DB2.DataItem("LH_COV_INS_GDL_PRM", "DTH_BNF_PLN_OPT_CD")
'colSubSet3.Add DB2.DataItem("LH_COV_INS_GDL_PRM", "RT_SEX_CD")
'colSubSet3.Add DB2.DataItem("LH_COV_INS_GDL_PRM", "RT_CLS_CD")
'colSubSet3.Add DB2.DataItem("LH_COV_INS_GDL_PRM", "GDL_PRM_AMT")
'colSubSet3.Add DB2.DataItem("LH_COV_INS_GDL_PRM", "GDL_PRM_UNT_QTY")
'colSubSet4.Add DB2.DataItem("LH_COV_INS_RNL_PER", "COV_PHA_NBR")
'colSubSet4.Add DB2.DataItem("LH_COV_INS_RNL_PER", "PLN_DES_SER_CD")
'colSubSet4.Add DB2.DataItem("LH_COV_INS_RNL_PER", "PRS_CD")
'colSubSet4.Add DB2.DataItem("LH_COV_INS_RNL_PER", "PRS_SEQ_NBR")
'colSubSet4.Add DB2.DataItem("LH_COV_INS_RNL_PER", "RENEWABLE_PRM_CD")
'colSubSet5.Add DB2.DataItem("LH_COV_INS_RNL_RT", "COV_PHA_NBR")
'colSubSet5.Add DB2.DataItem("LH_COV_INS_RNL_RT", "PRS_CD")
'colSubSet5.Add DB2.DataItem("LH_COV_INS_RNL_RT", "PRS_SEQ_NBR")
'colSubSet5.Add DB2.DataItem("LH_COV_INS_RNL_RT", "SEG_IDX_NBR")
'colSubSet5.Add DB2.DataItem("LH_COV_INS_RNL_RT", "PRM_RT_TYP_CD")
'colSubSet5.Add DB2.DataItem("LH_COV_INS_RNL_RT", "JT_INS_IND")
'colSubSet5.Add DB2.DataItem("LH_COV_INS_RNL_RT", "DTH_BNF_PLN_OPT_CD")
'colSubSet5.Add DB2.DataItem("LH_COV_INS_RNL_RT", "RT_SEX_CD")
'colSubSet5.Add DB2.DataItem("LH_COV_INS_RNL_RT", "RT_CLS_CD")
'colSubSet5.Add DB2.DataItem("LH_COV_INS_RNL_RT", "RT_BAN_CD")
'colSubSet5.Add DB2.DataItem("LH_COV_INS_RNL_RT", "RNL_RT")
'colSubSet6.Add DB2.DataItem("LH_SST_XTR_RNL_RT", "COV_PHA_NBR")
'colSubSet6.Add DB2.DataItem("LH_SST_XTR_RNL_RT", "PRS_CD")
'colSubSet6.Add DB2.DataItem("LH_SST_XTR_RNL_RT", "PRS_SEQ_NBR")
'colSubSet6.Add DB2.DataItem("LH_SST_XTR_RNL_RT", "SEG_IDX_NBR")
'colSubSet6.Add DB2.DataItem("LH_SST_XTR_RNL_RT", "PRM_RT_TYP_CD")
'colSubSet6.Add DB2.DataItem("LH_SST_XTR_RNL_RT", "SST_XTR_RT_TBL_CD")
'colSubSet6.Add DB2.DataItem("LH_SST_XTR_RNL_RT", "SST_XTR_PCT_IND")
'colSubSet6.Add DB2.DataItem("LH_SST_XTR_RNL_RT", "RT_SEX_CD")
'colSubSet6.Add DB2.DataItem("LH_SST_XTR_RNL_RT", "RT_CLS_CD")
'colSubSet6.Add DB2.DataItem("LH_SST_XTR_RNL_RT", "RT_BAN_CD")
'colSubSet6.Add DB2.DataItem("LH_SST_XTR_RNL_RT", "SST_XTR_UNT_AMT")
'colSubSet6.Add DB2.DataItem("LH_SST_XTR_RNL_RT", "SST_XTR_PCT")
'colSubSet7.Add DB2.DataItem("TH_COV_INS_RNL_RT", "COV_PHA_NBR")
'colSubSet7.Add DB2.DataItem("TH_COV_INS_RNL_RT", "PRS_CD")
'colSubSet7.Add DB2.DataItem("TH_COV_INS_RNL_RT", "PRS_SEQ_NBR")
'colSubSet7.Add DB2.DataItem("TH_COV_INS_RNL_RT", "SEG_IDX_NBR")
'colSubSet7.Add DB2.DataItem("TH_COV_INS_RNL_RT", "PRM_RT_TYP_CD")
'colSubSet7.Add DB2.DataItem("TH_COV_INS_RNL_RT", "JT_INS_IND")
'colSubSet7.Add DB2.DataItem("TH_COV_INS_RNL_RT", "RT_BAN_CD")
'colSubSet7.Add DB2.DataItem("TH_COV_INS_RNL_RT", "SST_RT_IND")
'
'
'ClusterSegItems.Add colSubset1
'ClusterSegItems.Add colSubset2
'ClusterSegItems.Add colSubSet3
'ClusterSegItems.Add colSubSet4
'ClusterSegItems.Add colSubSet5
'ClusterSegItems.Add colSubSet6
'ClusterSegItems.Add colSubSet7
'
''Populate colSegItems so there is one collection with all the data items.  this will be used if labels on all data items need to be adjusted or updated
'Dim item
'For Each CollectionItem In ClusterSegItems
'  For Each item In CollectionItem
'   colSegItems.Add item
'  Next
'Next
'End Sub
'
'
'Private Sub Segment75DataItems()
'
'colSegItems.Add DB2.DataItem("LH_POL_MVRY_VAL", "TOT_CRE_ITS_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_MVRY_VAL", "GUA_RT_ERN_ITS_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_MVRY_VAL", "MVRY_DT")
'colSegItems.Add DB2.DataItem("LH_POL_MVRY_VAL", "CSV_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_MVRY_VAL", "CINS_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_MVRY_VAL", "OTH_PRM_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_MVRY_VAL", "EXP_CRG_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_MVRY_VAL", "NAR_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_MVRY_VAL", "DEATH_BEN_AMT")
'colSegItems.Add DB2.DataItem("LH_POL_MVRY_VAL", "POL_DUR_NBR")
'
'End Sub
'
'Private Sub ToggleButton1_Click()
'   Dim item
'  For Each item In colSegItems
'    item.ShowBorders = ToggleButton1
'  Next
'
'End Sub

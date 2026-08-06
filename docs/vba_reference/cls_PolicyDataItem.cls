' Module: cls_PolicyDataItem.cls
' Type: Class Module
' Stream Path: VBA/cls_PolicyDataItem
' =========================================================

Attribute VB_Name = "cls_PolicyDataItem"
Attribute VB_Base = "0{FCFB3D2A-A0FA-1068-A738-08002B3371B5}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
Private colControls As Collection
Private colDisplayCards As Collection
Private dctSourceInfo As Dictionary
Private aryData() As Variant
Private blnFieldNotFound As Boolean
Private mTableName As String
Private mFieldName As String
Private mCount As Integer
Private mCommonName As String
Private mRegion As String
'Private mCobolName As String
'Private mPolicySegment As String
'Private mDocumentFolder  As String
'Private mDocumentFileName As String
'Private mDocumentBookmarkString As String

Public Sub classInitialize(sTableName As String, sFieldName As String, FieldValuesArray As Variant, SourceInfoDictionary As Dictionary)
    mTableName = sTableName
    mFieldName = sFieldName
    If IsEmpty(FieldValuesArray) Then
        blnFieldNotFound = True
        mCount = 0
    Else
        Set colControls = New Collection
        Set colDisplayCards = New Collection
        Set colMyLabels = New Collection
        Set dctSourceInfo = SourceInfoDictionary
      
        blnFieldNotFound = False
        aryData = FieldValuesArray
        mCount = UBound(aryData) + 1
        LoadDataMapInfo
    End If
End Sub
Public Property Get FieldNotFound()
    'A DataItem will be created for any requested Table.Field combination.
    'But if the data is not found in a table this property will return TRUE
    'This field should be check first before using other properties such as Value or NullZ
    FieldNotFound = blnFieldNotFound
End Property
Public Property Get ValueArray() As Variant
    ValueArray = aryData
End Property
Public Property Get value(Optional xcount As Integer = 1) As Variant
   value = aryData(xcount - 1)
End Property
Public Property Get NullZ(Optional xcount As Integer = 1, Optional IfNullValue As Variant = 0) As Variant
    'This function returns aryData if available and not equal to "Null".  Otherwise it returns the IfNullValue passed to the function
    If FieldNotFound Then
        NullZ = IfNullValue
    Else
        If aryData(xcount - 1) = "Null" Then
            NullZ = IfNullValue
        Else
            NullZ = aryData(xcount - 1)
        End If
    End If
End Property
Public Property Get Count() As Variant
    Count = mCount
End Property
Public Property Get Tablename() As String
    Tablename = mTableName
End Property
Public Property Get Fieldname() As String
    Fieldname = mFieldName
End Property
Public Property Get System() As String
    System = dctSourceInfo("System")
End Property
Public Property Get PolicyNumber() As String
    PolicyNumber = dctSourceInfo("PolicyNumber")
End Property
Public Property Get CompanyCode() As String
    CompanyCode = dctSourceInfo("CompanyCode")
End Property
Public Property Get SystemCode() As String
    SystemCode = dctSourceInfo("SystemCode")
End Property
Public Property Get DataName() As String
  DataName = mTableName & "." & mFieldName
End Property
Public Property Get CommonName() As String
  CommonName = mCommonName
End Property
Public Property Get CobolName() As String
 CobolName = mCobolName
End Property
'Public Function DocumentFullPath()
'  If mDocumentFolder = "none" Then
'    DocumentFullPath = "none"
'  Else
'    DocumentFullPath = DefaultCyberDocFolder & "\" & mDocumentFileName
'  End If
'End Function
'Public Property Get DocumentBookmarkString() As String
'  DocumentBookmarkString = mDocumentBookmarkString
'End Property
'
'Public Property Let ShowBorders(blnBorder As Boolean)
'  Dim item
'  For Each item In colControls
'     If blnBorder Then
'       item.GetControl.BorderColor = &H80000006
'     Else
'       item.GetControl.BorderColor = &H80000000
'     End If
'  Next
'End Property
'
'Public Sub AddControl(Cntrl As MSForms.Control, Optional HelpLabel As Variant)
'  Dim ControlEvent As cls_ControlEvents
'  Set ControlEvent = New cls_ControlEvents
'  ControlEvent.classInitialize Cntrl, Me
'
'  colControls.Add ControlEvent
'
'  If Not IsMissing(HelpLabel) Then Set ControlEvent.HelpTextLabel = HelpLabel
'  Set ControlEvent = Nothing
'End Sub
'
'Public Sub DisplayDataCard()
'  Dim frm As frmDataCardPrimary
'  Set frm = New frmDataCardPrimary
'  frm.FormInitialize mCommonName, System, TableName & "." & FieldName, mCobolName, mPolicySegment ',  Me.DocumentFullPath, Me.DocumentBookmarkString
'  colDisplayCards.Add frm
'  frm.Show vbModeless
'  Set frm = Nothing
'End Sub
'
Private Sub LoadDataMapInfo()
  GetDataMap.Filter = "TableName = '" & mTableName & "' AND FieldName = '" & mFieldName & "'"
  If GetDataMap.EOF And GetDataMap.BOF Then
    mCommonName = "Not Found"
    mCobolName = "Not Found"
    mPolicySegment = "Not Found"
    mDocumentFolder = "Not Found"
    mDocumentFileName = "Not Found"
    mDocumentBookmarkString = "Not Found"
  Else
    mCommonName = GetDataMap.Fields("CommonName")
    mCobolName = GetDataMap.Fields("CobolName")
    mPolicySegment = GetDataMap.Fields("SegmentID")
    mDocumentFolder = GetDataMap.Fields("DocumentationFolder")
    mDocumentFileName = GetDataMap.Fields("DocumentationFileName").value
    mDocumentBookmarkString = GetDataMap.Fields("DocumentationBookmark").value
  End If
End Sub


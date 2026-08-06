' Module: mdlFunctions_Targets.bas
' Type: Standard Module
' Stream Path: VBA/mdlFunctions_Targets
' =========================================================

Attribute VB_Name = "mdlFunctions_Targets"
'Dim oRates As cls_Rates
'Dim blnInitialized As Boolean
'Private Sub InitializeModule()
'    Set oRates = New cls_Rates
'    blnInitialized = True
'End Sub
'
'
'Public Function CommissionTargetPremium(PolicyFile As udtPolicyFile, Optional Storage As cls_Storage) As Double
'If Not blnInitialized Then InitializeModule
'
'
'Dim x As Integer
'Dim PolicyBand As Integer, RiderBand As Integer
'Dim subtotal As Double
'Dim CTPR As Double
'Dim TBL1CTPR As Double
'Dim TableRating As Double
'Dim Flat As Double
'Dim ValuationDate As Date
'Dim Target As Double
'
'PolicyBand = GetPolicyBand(PolicyFile.BaseCovs, PolicyFile.PolicyValues.ValuationDate)
'
'With PolicyFile
'ValuationDate = .PolicyValues.ValuationDate
'With .BaseCovs
'    For x = 1 To UBound(.IssueAge)
'        CTPR = oRates.CTP(.Plancode(x), .IssueAge(x), .Sex(x), .Rateclass(x), PolicyBand)
'        TBL1CTPR = oRates.TBL1CTP(.Plancode(x), .IssueAge(x), .Sex(x), .Rateclass(x), PolicyBand)
'        CTPR = CTPR + .TableRating(x) * TBL1CTPR
'
'        If .Flat(x) > 0 Then
'            If ValuationDate < .FlatCeaseDate(x) Then
'                CTPR = CTPR + .Flat(x)
'            End If
'        End If
'        Target = .Amount(x) / 1000 * CTPR
'        subtotal = subtotal + Target
'    Next
'End With 'BaseCovs
'
'With .RiderCovs
'    For x = 1 To UBound(.IssueAge)
'        If ValuationDate >= .IssueDate(x) And ValuationDate < .MaturityDate(x) Then
'            RiderBand = GetRiderBand((.Plancode(x)), .Amount(x))
'            CTPR = oRates.CTP(.Plancode(x), .IssueAge(x), .Sex(x), .Rateclass(x), RiderBand)
'            TBL1CTPR = oRates.TBL1CTP(.Plancode(x), .IssueAge(x), .Sex(x), .Rateclass(x), RiderBand)
'            CTPR = CTPR + .TableRating(x) * TBL1CTPR
'
'            If .Flat(x) > 0 Then
'                If ValuationDate < .FlatCeaseDate(x) Then
'                    CTPR = CTPR + .Flat(x)
'                End If
'            End If
'            Target = .Amount(x) / 1000 * CTPR
'            subtotal = subtotal + Target
'        End If
'    Next
'End With 'RiderCovs
'
'If .PWoT.OnPolicy Then
'    With .PWoT
'        CTPR = oRates.BENCTP(PolicyFile.BaseCovs.Plancode(1), .IssueAge, PolicyFile.BaseCovs.Sex(1), PolicyFile.BaseCovs.Rateclass(1), PolicyBand, "PWoT")
'        CTPR = CTPR * (1 + 0.25 * .TableRating)
'        Target = .Amount * CTPR
'        subtotal = subtotal + Target
'    End With 'PWoT
'End If
'
'If .GIO.OnPolicy Then
'    With .GIO
'        CTPR = oRates.BENCTP(PolicyFile.BaseCovs.Plancode(1), .IssueAge, PolicyFile.BaseCovs.Sex(1), PolicyFile.BaseCovs.Rateclass(1), PolicyBand, "GIO")
'        CTPR = CTPR * (1 + 0.25 * .TableRating)
'        Target = .Amount * CTPR
'        subtotal = subtotal + Target
'    End With 'GIO
'End If
'
''PWoC must be calcluated last since it depends on the CTP from other coverages
'If .PWoC.OnPolicy Then
'    With .PWoC
'        CTPR = oRates.BENCTP(PolicyFile.BaseCovs.Plancode(1), .IssueAge, PolicyFile.BaseCovs.Sex(1), PolicyFile.BaseCovs.Rateclass(1), PolicyBand, "PWoC")
'        CTPR = CTPR * (1 + 0.25 * .TableRating)
'        'The Amount for PWoC is the total min premium of the other coverages
'        Target = subtotal * CTPR
'        subtotal = subtotal + Target
'    End With 'PWoC
'End If
'End With 'PolicyFile
'CommissionTargetPremium = subtotal
'End Function
'
'
'Public Function MinimumTargetPremium(PolicyFile As udtPolicyFile, Optional Storage As cls_Storage) As Double
'If Not blnInitialized Then InitializeModule
'
'Dim x As Integer
'Dim PolicyBand As Integer, RiderBand As Integer
'Dim subtotal As Double
'Dim MTPR As Double
'Dim TBL1MTPR As Double
'Dim TableRating As Double
'Dim Flat As Double
'Dim ValuationDate As Date
'Dim Target As Double
'
'PolicyBand = GetPolicyBand(PolicyFile.BaseCovs, PolicyFile.PolicyValues.ValuationDate)
'
'With PolicyFile
'ValuationDate = .PolicyValues.ValuationDate
'With .BaseCovs
'    For x = 1 To UBound(.IssueAge)
'        MTPR = oRates.MTP(.Plancode(x), .IssueAge(x), .Sex(x), .Rateclass(x), PolicyBand)
'        TBL1MTPR = oRates.TBL1MTP(.Plancode(x), .IssueAge(x), .Sex(x), .Rateclass(x), PolicyBand)
'        MTPR = MTPR + .TableRating(x) * TBL1MTPR
'
'        If .Flat(x) > 0 Then
'            If ValuationDate < .FlatCeaseDate(x) Then
'                MTPR = MTPR + .Flat(x)
'            End If
'        End If
'        Target = .Amount(x) / 1000 * MTPR
'        subtotal = subtotal + Target
'    Next
'End With 'BaseCovs
'
'With .RiderCovs
'    For x = 1 To UBound(.IssueAge)
'        If ValuationDate >= .IssueDate(x) And ValuationDate < .MaturityDate(x) Then
'            RiderBand = GetRiderBand(.Plancode(x), .Amount(x))
'            MTPR = oRates.MTP(.Plancode(x), .IssueAge(x), .Sex(x), .Rateclass(x), RiderBand)
'            TBL1MTPR = oRates.TBL1MTP(.Plancode(x), .IssueAge(x), .Sex(x), .Rateclass(x), RiderBand)
'            MTPR = MTPR + .TableRating(x) * TBL1MTPR
'
'            If .Flat(x) > 0 Then
'                If ValuationDate < .FlatCeaseDate(x) Then
'                    MTPR = MTPR + .Flat(x)
'                End If
'            End If
'            Target = .Amount(x) / 1000 * MTPR
'            subtotal = subtotal + Target
'        End If
'    Next
'End With 'RiderCovs
'
'If .PWoT.OnPolicy Then
'    With .PWoT
'        MTPR = oRates.BENMTP(PolicyFile.BaseCovs.Plancode(1), .IssueAge, PolicyFile.BaseCovs.Sex(1), PolicyFile.BaseCovs.Rateclass(1), PolicyBand, "PWoT")
'        MTPR = MTPR * (1 + 0.25 * .TableRating)
'        Target = .Amount * MTPR
'        subtotal = subtotal + Target
'    End With 'PWoT
'End If
'
'If .GIO.OnPolicy Then
'    With .GIO
'        MTPR = oRates.BENMTP(PolicyFile.BaseCovs.Plancode(1), .IssueAge, PolicyFile.BaseCovs.Sex(1), PolicyFile.BaseCovs.Rateclass(1), PolicyBand, "GIO")
'        MTPR = MTPR * (1 + 0.25 * .TableRating)
'        Target = .Amount * MTPR
'        subtotal = subtotal + Target
'    End With 'GIO
'End If
'
''PWoC must be calcluated last since it depends on the MTP from other coverages
'If .PWoC.OnPolicy Then
'    With .PWoC
'        MTPR = oRates.BENMTP(PolicyFile.BaseCovs.Plancode(1), .IssueAge, PolicyFile.BaseCovs.Sex(1), PolicyFile.BaseCovs.Rateclass(1), PolicyBand, "PWoC")
'        MTPR = MTPR * (1 + 0.25 * .TableRating)
'        'The Amount for PWoC is the total min premium of the other coverages
'        Target = subtotal * MTPR
'        subtotal = subtotal + Target
'    End With 'PWoC
'End If
'End With 'PolicyFile
'MinimumTargetPremium = subtotal
'End Function
'
'
'Private Function GetPolicyBand(BaseCovs As udtCoverages, ValuationDate As Date) As Integer
'Dim x As Integer
'Dim TotalAmt As Double
'
'With BaseCovs
'    For x = 1 To UBound(.IssueAge)
'        If ValuationDate >= .IssueDate(x) And ValuationDate < .MaturityDate(x) Then
'            TotalAmt = TotalAmt + .Amount(x)
'        End If
'    Next
'    GetPolicyBand = oRates.Band(.Plancode(1), TotalAmt)
'End With
'
'End Function
'
'Private Function GetRiderBand(Plancode As String, Amount As Double)
'    GetRiderBand = oRates.Band(Plancode, Amount)
'End Function
